import json
from decimal import Decimal, ROUND_HALF_UP
from datetime import date, timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from django.db.models import Sum
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from .models import (Employee, Machine, Design, Attendance, WorkEntry,
                     SalaryPayment,
                     Production, Advance, Salary, Party, Product,
                     Bill, BillItem, Challan, ChallanItem, Expense)


# ── Helpers ──────────────────────────────────────────────────────────────────

def round_hours(total_minutes):
    """
    Rounding rules:
      < 15 min  →  ignore (floor)
      15–29 min →  +0.5
      ≥ 30 min  →  +1.0
    """
    full = total_minutes // 60
    mins = total_minutes % 60
    if mins < 15:
        return Decimal(full)
    elif mins < 30:
        return Decimal(full) + Decimal('0.5')
    else:
        return Decimal(full + 1)


def emp_required(fn):
    def wrap(request, *args, **kw):
        if not request.session.get('employee_id'):
            return redirect('emp_login')
        return fn(request, *args, **kw)
    wrap.__name__ = fn.__name__
    return wrap


def adm_required(fn):
    def wrap(request, *args, **kw):
        if not request.session.get('is_admin'):
            return redirect('adm_login')
        return fn(request, *args, **kw)
    wrap.__name__ = fn.__name__
    return wrap


def _rebuild_challan_from_bill(bill):
    """Delete all challan items and rebuild from bill items (auto-sync)."""
    try:
        challan = bill.challan
    except Challan.DoesNotExist:
        challan = Challan.objects.create(
            bill=bill,
            challan_number=bill.bill_number,
            party=bill.party,
            date=bill.date,
        )
    # keep manual edits of price but sync products/qty
    challan.items.all().delete()
    challan.party = bill.party
    challan.date = bill.date
    total = Decimal('0')
    for item in bill.items.all():
        t = item.quantity * item.product.challan_price
        total += t
        ChallanItem.objects.create(
            challan=challan,
            product=item.product,
            quantity=item.quantity,
            price=item.product.challan_price,
            total=t,
        )
    challan.total_amount = total
    challan.save()
    return challan


# ── EMPLOYEE AUTH ─────────────────────────────────────────────────────────────

def emp_login(request):
    error = ''
    if request.method == 'POST':
        uid = request.POST.get('user_id', '').strip()
        pw = request.POST.get('password', '').strip()
        try:
            emp = Employee.objects.get(user_id=uid, password=pw, is_active=True)
            request.session['employee_id'] = emp.id
            request.session['employee_name'] = emp.name
            return redirect('emp_dashboard')
        except Employee.DoesNotExist:
            error = 'गलत यूजर आईडी या पासवर्ड!'
    return render(request, 'employee/login.html', {'error': error})


def emp_logout(request):
    request.session.flush()
    return redirect('emp_login')


# ── EMPLOYEE DASHBOARD ────────────────────────────────────────────────────────

@emp_required
def emp_dashboard(request):
    emp = get_object_or_404(Employee, id=request.session['employee_id'])
    today = timezone.localdate()

    # Current open session (entered but not exited)
    open_att = Attendance.objects.filter(
        employee=emp, date=today, exit_time__isnull=True
    ).order_by('-entry_time').first()
    is_inside = open_att is not None

    # Monthly stats
    m, y = today.month, today.year
    month_atts = Attendance.objects.filter(employee=emp, date__month=m, date__year=y)
    working_days = month_atts.values('date').distinct().count()
    total_hours  = month_atts.aggregate(h=Sum('total_hours'))['h'] or Decimal('0')
    salary_earned = total_hours * emp.salary_per_hour
    pending_adv   = Advance.objects.filter(employee=emp, is_deducted=False).aggregate(t=Sum('amount'))['t'] or Decimal('0')
    today_hours   = Attendance.objects.filter(employee=emp, date=today).aggregate(h=Sum('total_hours'))['h'] or Decimal('0')

    # 7-day chart
    labels, data = [], []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        h = Attendance.objects.filter(employee=emp, date=d).aggregate(h=Sum('total_hours'))['h'] or 0
        labels.append(d.strftime('%d %b'))
        data.append(float(h))

    return render(request, 'employee/dashboard.html', {
        'emp': emp, 'today': today,
        'is_inside': is_inside, 'open_att': open_att,
        'working_days': working_days, 'total_hours': total_hours,
        'salary_earned': salary_earned, 'net_salary': salary_earned - pending_adv,
        'today_hours': today_hours,
        'chart_labels': json.dumps(labels), 'chart_data': json.dumps(data),
    })


# ── ATTENDANCE ENTRY / EXIT ───────────────────────────────────────────────────

@emp_required
def mark_entry(request):
    if request.method == 'POST':
        emp = get_object_or_404(Employee, id=request.session['employee_id'])
        Attendance.objects.create(employee=emp, date=timezone.localdate(), entry_time=timezone.now())
        messages.success(request, f'प्रवेश दर्ज! ✅')
    return redirect('emp_dashboard')


@emp_required
def mark_exit(request):
    emp = get_object_or_404(Employee, id=request.session['employee_id'])
    att = Attendance.objects.filter(employee=emp, exit_time__isnull=True).order_by('-entry_time').first()
    if not att:
        messages.error(request, 'पहले प्रवेश करें!')
        return redirect('emp_dashboard')

    if request.method == 'POST':
        shift      = request.POST.get('shift', 'day')
        katay      = int(request.POST.get('katay', 1))
        mts_choice = request.POST.get('mts_choice', '24')
        custom_mts = request.POST.get('custom_mts', '0')

        mts_per_katay = Decimal(custom_mts if mts_choice == '0' else mts_choice)
        total_mts     = Decimal(katay) * mts_per_katay

        # Calculate time
        exit_time = timezone.now()
        att.exit_time = exit_time
        total_minutes = int((exit_time - att.entry_time).total_seconds() / 60)
        att.total_hours = round_hours(total_minutes)
        att.save()

        we = WorkEntry.objects.create(
            attendance=att, shift=shift,
            katay=katay, mts_per_katay=mts_per_katay, total_mts=total_mts
        )

        # Proportional production split by patti count
        if emp.machine:
            designs = list(emp.machine.designs.all())
            total_patti = sum(d.patti_count for d in designs)
            if total_patti > 0:
                for d in designs:
                    prop = Decimal(d.patti_count) / Decimal(total_patti)
                    Production.objects.create(
                        work_entry=we, design=d,
                        mts_produced=(total_mts * prop).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
                        date=timezone.localdate()
                    )

        messages.success(request, f'बाहर दर्ज! कुल घंटे: {att.total_hours} ✅')
        return redirect('emp_dashboard')

    return render(request, 'employee/work_form.html', {'att': att})


@emp_required
def emp_history(request):
    emp = get_object_or_404(Employee, id=request.session['employee_id'])
    atts = Attendance.objects.filter(employee=emp).select_related('work_entry').order_by('-date', '-entry_time')
    return render(request, 'employee/history.html', {'emp': emp, 'atts': atts})


# ── ADMIN AUTH ────────────────────────────────────────────────────────────────

def adm_login(request):
    error = ''
    if request.method == 'POST':
        u = request.POST.get('username', '')
        p = request.POST.get('password', '')
        if u == 'admin' and p == 'admin123':
            request.session['is_admin'] = True
            return redirect('adm_dashboard')
        error = 'Invalid credentials!'
    return render(request, 'admin/login.html', {'error': error})


def adm_logout(request):
    request.session.flush()
    return redirect('adm_login')


# ── ADMIN DASHBOARD ───────────────────────────────────────────────────────────

@adm_required
def adm_dashboard(request):
    today = timezone.localdate()
    m, y = today.month, today.year

    total_emp  = Employee.objects.filter(is_active=True).count()
    total_prod = Production.objects.filter(date__month=m, date__year=y).aggregate(t=Sum('mts_produced'))['t'] or Decimal('0')
    total_exp  = Expense.objects.filter(date__month=m, date__year=y).aggregate(t=Sum('amount'))['t'] or Decimal('0')

    # Salary this month (calculated from attendance)
    total_salary = Decimal('0')
    for e in Employee.objects.filter(is_active=True):
        h = Attendance.objects.filter(employee=e, date__month=m, date__year=y).aggregate(h=Sum('total_hours'))['h'] or 0
        total_salary += Decimal(str(h)) * e.salary_per_hour

    # Revenue from challans (challan price = actual selling price)
    challan_revenue = ChallanItem.objects.filter(
        challan__date__month=m, challan__date__year=y
    ).aggregate(t=Sum('total'))['t'] or Decimal('0')

    # Revenue from bills (billing price)
    bill_revenue = Bill.objects.filter(
        date__month=m, date__year=y
    ).aggregate(t=Sum('total_amount'))['t'] or Decimal('0')

    # Net income = challan revenue - all expenses (salary + other expenses)
    total_all_exp = total_exp + total_salary
    net_income = challan_revenue - total_all_exp

    # 7-day production chart
    p_labels, p_data = [], []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        v = Production.objects.filter(date=d).aggregate(t=Sum('mts_produced'))['t'] or 0
        p_labels.append(d.strftime('%d %b'))
        p_data.append(float(v))

    # 7-day revenue chart (challan based)
    r_labels, r_data = [], []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        v = ChallanItem.objects.filter(challan__date=d).aggregate(t=Sum('total'))['t'] or 0
        r_labels.append(d.strftime('%d %b'))
        r_data.append(float(v))

    # Expense pie (include salary as a category)
    exp_cats, exp_vals = [], []
    for code, name in Expense.CATEGORY_CHOICES:
        v = Expense.objects.filter(date__month=m, date__year=y, category=code).aggregate(t=Sum('amount'))['t'] or 0
        if v > 0:
            exp_cats.append(name)
            exp_vals.append(float(v))
    if total_salary > 0:
        exp_cats.append('Salary')
        exp_vals.append(float(total_salary))

    return render(request, 'admin/dashboard.html', {
        'total_emp': total_emp, 'total_prod': total_prod,
        'total_exp': total_exp, 'total_salary': total_salary,
        'challan_revenue': challan_revenue,
        'bill_revenue': bill_revenue,
        'net_income': net_income,
        'total_all_exp': total_all_exp,
        'p_labels': json.dumps(p_labels), 'p_data': json.dumps(p_data),
        'r_labels': json.dumps(r_labels), 'r_data': json.dumps(r_data),
        'exp_cats': json.dumps(exp_cats), 'exp_vals': json.dumps(exp_vals),
    })


# ── EMPLOYEE CRUD ─────────────────────────────────────────────────────────────

@adm_required
def emp_list(request):
    emps = Employee.objects.select_related('machine').all()
    return render(request, 'admin/emp_list.html', {'emps': emps})


@adm_required
def emp_add(request):
    machines = Machine.objects.all()
    if request.method == 'POST':
        try:
            Employee.objects.create(
                name=request.POST['name'],
                user_id=request.POST['user_id'],
                password=request.POST['password'],
                machine_id=request.POST.get('machine') or None,
                joining_date=request.POST['joining_date'],
                salary_per_hour=request.POST['salary_per_hour'],
            )
            messages.success(request, 'Employee added!')
            return redirect('emp_list')
        except Exception as e:
            messages.error(request, f'Error: {e}')
    return render(request, 'admin/emp_form.html', {'machines': machines, 'title': 'Add Employee', 'obj': None})


@adm_required
def emp_edit(request, pk):
    emp = get_object_or_404(Employee, pk=pk)
    machines = Machine.objects.all()
    if request.method == 'POST':
        try:
            emp.name = request.POST['name']
            emp.user_id = request.POST['user_id']
            emp.password = request.POST['password']
            emp.machine_id = request.POST.get('machine') or None
            emp.joining_date = request.POST['joining_date']
            emp.salary_per_hour = request.POST['salary_per_hour']
            emp.is_active = 'is_active' in request.POST
            emp.save()
            messages.success(request, 'Employee updated!')
            return redirect('emp_list')
        except Exception as e:
            messages.error(request, f'Error: {e}')
    return render(request, 'admin/emp_form.html', {'machines': machines, 'title': 'Edit Employee', 'obj': emp})


@adm_required
def emp_delete(request, pk):
    emp = get_object_or_404(Employee, pk=pk)
    if request.method == 'POST':
        emp.delete()
        messages.success(request, 'Employee deleted!')
        return redirect('emp_list')
    return render(request, 'admin/confirm_delete.html', {'obj': emp, 'back': 'emp_list'})


# ── MACHINE CRUD ──────────────────────────────────────────────────────────────

@adm_required
def machine_list(request):
    machines = Machine.objects.prefetch_related('designs').all()
    return render(request, 'admin/machine_list.html', {'machines': machines})


@adm_required
def machine_add(request):
    if request.method == 'POST':
        try:
            Machine.objects.create(machine_number=request.POST['machine_number'], category=request.POST['category'])
            messages.success(request, 'Machine added!')
            return redirect('machine_list')
        except Exception as e:
            messages.error(request, f'Error: {e}')
    return render(request, 'admin/machine_form.html', {'title': 'Add Machine', 'obj': None})


@adm_required
def machine_edit(request, pk):
    m = get_object_or_404(Machine, pk=pk)
    if request.method == 'POST':
        try:
            m.machine_number = request.POST['machine_number']
            m.category = request.POST['category']
            m.save()
            messages.success(request, 'Machine updated!')
            return redirect('machine_list')
        except Exception as e:
            messages.error(request, f'Error: {e}')
    return render(request, 'admin/machine_form.html', {'title': 'Edit Machine', 'obj': m})


@adm_required
def machine_delete(request, pk):
    m = get_object_or_404(Machine, pk=pk)
    if request.method == 'POST':
        m.delete(); messages.success(request, 'Machine deleted!')
        return redirect('machine_list')
    return render(request, 'admin/confirm_delete.html', {'obj': m, 'back': 'machine_list'})


# ── DESIGN CRUD ───────────────────────────────────────────────────────────────

@adm_required
def design_list(request):
    designs = Design.objects.select_related('machine').all()
    return render(request, 'admin/design_list.html', {'designs': designs})


@adm_required
def design_add(request):
    machines = Machine.objects.all()
    if request.method == 'POST':
        try:
            Design.objects.create(machine_id=request.POST['machine'], design_name=request.POST['design_name'], patti_count=request.POST['patti_count'])
            messages.success(request, 'Design added!')
            return redirect('design_list')
        except Exception as e:
            messages.error(request, f'Error: {e}')
    return render(request, 'admin/design_form.html', {'machines': machines, 'title': 'Add Design', 'obj': None})


@adm_required
def design_edit(request, pk):
    d = get_object_or_404(Design, pk=pk)
    machines = Machine.objects.all()
    if request.method == 'POST':
        try:
            d.machine_id = request.POST['machine']
            d.design_name = request.POST['design_name']
            d.patti_count = request.POST['patti_count']
            d.save(); messages.success(request, 'Design updated!')
            return redirect('design_list')
        except Exception as e:
            messages.error(request, f'Error: {e}')
    return render(request, 'admin/design_form.html', {'machines': machines, 'title': 'Edit Design', 'obj': d})


@adm_required
def design_delete(request, pk):
    d = get_object_or_404(Design, pk=pk)
    if request.method == 'POST':
        d.delete(); messages.success(request, 'Design deleted!')
        return redirect('design_list')
    return render(request, 'admin/confirm_delete.html', {'obj': d, 'back': 'design_list'})


# ── ADVANCE ───────────────────────────────────────────────────────────────────

@adm_required
def advance_list(request):
    advances = Advance.objects.select_related('employee').all()
    return render(request, 'admin/advance_list.html', {'advances': advances})


@adm_required
def advance_add(request):
    emps = Employee.objects.filter(is_active=True)
    if request.method == 'POST':
        try:
            Advance.objects.create(
                employee_id=request.POST['employee'],
                amount=request.POST['amount'],
                date=request.POST['date'],
                note=request.POST.get('note', '')
            )
            messages.success(request, 'Advance added!')
            return redirect('advance_list')
        except Exception as e:
            messages.error(request, f'Error: {e}')
    return render(request, 'admin/advance_form.html', {'emps': emps})


# ── PARTY CRUD ────────────────────────────────────────────────────────────────

@adm_required
def party_list(request):
    parties = Party.objects.all()
    return render(request, 'admin/party_list.html', {'parties': parties})


@adm_required
def party_add(request):
    if request.method == 'POST':
        try:
            Party.objects.create(name=request.POST['name'], gst_number=request.POST.get('gst_number',''), address=request.POST.get('address',''), phone=request.POST.get('phone',''))
            messages.success(request, 'Party added!')
            return redirect('party_list')
        except Exception as e:
            messages.error(request, f'Error: {e}')
    return render(request, 'admin/party_form.html', {'title': 'Add Party', 'obj': None})


@adm_required
def party_edit(request, pk):
    p = get_object_or_404(Party, pk=pk)
    if request.method == 'POST':
        try:
            p.name=request.POST['name']; p.gst_number=request.POST.get('gst_number','')
            p.address=request.POST.get('address',''); p.phone=request.POST.get('phone','')
            p.save(); messages.success(request, 'Party updated!')
            return redirect('party_list')
        except Exception as e:
            messages.error(request, f'Error: {e}')
    return render(request, 'admin/party_form.html', {'title': 'Edit Party', 'obj': p})


@adm_required
def party_delete(request, pk):
    p = get_object_or_404(Party, pk=pk)
    if request.method == 'POST':
        p.delete(); messages.success(request, 'Party deleted!')
        return redirect('party_list')
    return render(request, 'admin/confirm_delete.html', {'obj': p, 'back': 'party_list'})


# ── PRODUCT CRUD ──────────────────────────────────────────────────────────────

@adm_required
def product_list(request):
    products = Product.objects.all()
    return render(request, 'admin/product_list.html', {'products': products})


@adm_required
def product_add(request):
    if request.method == 'POST':
        try:
            Product.objects.create(
                design_name=request.POST['design_name'],
                hsn_code=request.POST.get('hsn_code', ''),
                unit=request.POST.get('unit', 'MTR'),
                manufacturing_price=request.POST['manufacturing_price'],
                billing_price=request.POST['billing_price'],
                challan_price=request.POST['challan_price'],
                gst_percent=request.POST.get('gst_percent') or 0,
            )
            messages.success(request, 'Product added!')
            return redirect('product_list')
        except Exception as e:
            messages.error(request, f'Error: {e}')
    return render(request, 'admin/product_form.html', {'title': 'Add Product', 'obj': None})


@adm_required
def product_edit(request, pk):
    p = get_object_or_404(Product, pk=pk)
    UNITS = Product.UNIT_CHOICES
    if request.method == 'POST':
        try:
            p.design_name=request.POST['design_name']
            p.hsn_code=request.POST.get('hsn_code','')
            p.unit=request.POST.get('unit','MTR')
            p.manufacturing_price=request.POST['manufacturing_price']
            p.billing_price=request.POST['billing_price']
            p.challan_price=request.POST['challan_price']
            p.gst_percent=request.POST.get('gst_percent') or 0
            p.save(); messages.success(request, 'Product updated!')
            return redirect('product_list')
        except Exception as e:
            messages.error(request, f'Error: {e}')
    return render(request, 'admin/product_form.html', {'title': 'Edit Product', 'obj': p, 'units': UNITS})


@adm_required
def product_delete(request, pk):
    p = get_object_or_404(Product, pk=pk)
    if request.method == 'POST':
        p.delete(); messages.success(request, 'Product deleted!')
        return redirect('product_list')
    return render(request, 'admin/confirm_delete.html', {'obj': p, 'back': 'product_list'})


# ── BILL ──────────────────────────────────────────────────────────────────────

@adm_required
def bill_list(request):
    bills = Bill.objects.select_related('party').order_by('-date')
    return render(request, 'admin/bill_list.html', {'bills': bills})


def _next_bill_number():
    """
    Auto-generate next bill number.
    Finds the last bill, extracts numeric part, adds 1.
    Examples:
      Last bill '4'     → '5'
      Last bill 'INV-4' → 'INV-5'
      Last bill 'BILL004' → 'BILL005'
      No bills yet → '1'
    """
    import re
    last = Bill.objects.order_by('-created_at').first()
    if not last:
        return '1'
    num = last.bill_number.strip()
    # Find trailing number in the bill number string
    match = re.search(r'(\d+)$', num)
    if match:
        prefix = num[:match.start()]
        next_n = int(match.group()) + 1
        # Keep same zero-padding if original had it e.g. '004' → '005'
        if match.group().startswith('0') and len(match.group()) > 1:
            return prefix + str(next_n).zfill(len(match.group()))
        return prefix + str(next_n)
    # No number found — just append 1
    return num + '-1'


@adm_required
def bill_create(request):
    parties = Party.objects.all()
    products = Product.objects.all()
    today = date.today()
    if request.method == 'POST':
        try:
            apply_gst = request.POST.get('apply_gst') == 'on'
            is_igst   = request.POST.get('is_igst') == 'on'
            bill = Bill.objects.create(
                bill_number=request.POST['bill_number'],
                party_id=request.POST['party'],
                date=request.POST['date'],
                apply_gst=apply_gst,
                is_igst=is_igst,
                notes=request.POST.get('notes', '')
            )
            pids = request.POST.getlist('product_id[]')
            qtys = request.POST.getlist('quantity[]')
            subtotal = Decimal('0'); total_gst = Decimal('0')
            for pid, qty in zip(pids, qtys):
                if pid and qty and Decimal(qty) > 0:
                    prod = Product.objects.get(pk=pid)
                    base = Decimal(qty) * prod.billing_price
                    gst_amt = (base * prod.gst_percent / 100).quantize(Decimal('0.01')) if apply_gst and prod.gst_percent > 0 else Decimal('0')
                    subtotal += base; total_gst += gst_amt
                    BillItem.objects.create(
                        bill=bill, product=prod, quantity=qty,
                        price=prod.billing_price,
                        hsn_code=prod.hsn_code, unit=prod.unit,
                        gst_percent=prod.gst_percent if apply_gst else Decimal('0'),
                        gst_amount=gst_amt, total=base + gst_amt
                    )
            bill.subtotal = subtotal; bill.gst_amount = total_gst
            # Split GST into SGST+CGST or IGST
            if apply_gst:
                if is_igst:
                    bill.igst_amount = total_gst; bill.sgst_amount = Decimal('0'); bill.cgst_amount = Decimal('0')
                else:
                    half = (total_gst / 2).quantize(Decimal('0.01'))
                    bill.sgst_amount = half; bill.cgst_amount = total_gst - half; bill.igst_amount = Decimal('0')
            bill.total_amount = subtotal + total_gst
            bill.save()
            _rebuild_challan_from_bill(bill)
            messages.success(request, f'Bill #{bill.bill_number} created! Challan auto-generated.')
            return redirect('bill_detail', pk=bill.pk)
        except Exception as e:
            messages.error(request, f'Error: {e}')
    next_num = _next_bill_number()
    return render(request, 'admin/bill_form.html', {'today': today, 'parties': parties, 'products': products, 'title': 'Create Bill', 'obj': None, 'next_bill_number': next_num})


@adm_required
def bill_edit(request, pk):
    bill = get_object_or_404(Bill, pk=pk)
    parties = Party.objects.all()
    products = Product.objects.all()
    today = date.today()
    if request.method == 'POST':
        try:
            apply_gst = request.POST.get('apply_gst') == 'on'
            is_igst   = request.POST.get('is_igst') == 'on'
            bill.bill_number = request.POST['bill_number']; bill.party_id = request.POST['party']
            bill.date = request.POST['date']; bill.apply_gst = apply_gst
            bill.is_igst = is_igst; bill.notes = request.POST.get('notes', '')
            bill.items.all().delete()
            pids = request.POST.getlist('product_id[]'); qtys = request.POST.getlist('quantity[]')
            subtotal = Decimal('0'); total_gst = Decimal('0')
            for pid, qty in zip(pids, qtys):
                if pid and qty and Decimal(qty) > 0:
                    prod = Product.objects.get(pk=pid)
                    base = Decimal(qty) * prod.billing_price
                    gst_amt = (base * prod.gst_percent / 100).quantize(Decimal('0.01')) if apply_gst and prod.gst_percent > 0 else Decimal('0')
                    subtotal += base; total_gst += gst_amt
                    BillItem.objects.create(
                        bill=bill, product=prod, quantity=qty,
                        price=prod.billing_price,
                        hsn_code=prod.hsn_code, unit=prod.unit,
                        gst_percent=prod.gst_percent if apply_gst else Decimal('0'),
                        gst_amount=gst_amt, total=base + gst_amt
                    )
            bill.subtotal = subtotal; bill.gst_amount = total_gst
            if apply_gst:
                if is_igst:
                    bill.igst_amount = total_gst; bill.sgst_amount = Decimal('0'); bill.cgst_amount = Decimal('0')
                else:
                    half = (total_gst / 2).quantize(Decimal('0.01'))
                    bill.sgst_amount = half; bill.cgst_amount = total_gst - half; bill.igst_amount = Decimal('0')
            bill.total_amount = subtotal + total_gst
            bill.save()
            _rebuild_challan_from_bill(bill)
            messages.success(request, 'Bill updated! Challan auto-synced.')
            return redirect('bill_detail', pk=bill.pk)
        except Exception as e:
            messages.error(request, f'Error: {e}')
    return render(request, 'admin/bill_form.html', {'today': today, 'parties': parties, 'products': products, 'title': 'Edit Bill', 'obj': bill})


@adm_required
def bill_detail(request, pk):
    from .models import CompanyProfile
    bill = get_object_or_404(Bill, pk=pk)
    company = CompanyProfile.objects.first()
    amount_words = _amount_in_words(bill.total_amount)
    return render(request, 'admin/bill_detail.html', {
        'bill': bill, 'company': company, 'amount_words': amount_words,
    })


@adm_required
def bill_delete(request, pk):
    bill = get_object_or_404(Bill, pk=pk)
    if request.method == 'POST':
        bill.delete(); messages.success(request, 'Bill deleted!')
        return redirect('bill_list')
    return render(request, 'admin/confirm_delete.html', {'obj': bill, 'back': 'bill_list'})


# ── CHALLAN ───────────────────────────────────────────────────────────────────

@adm_required
def challan_list(request):
    from django.http import HttpResponse
    import csv

    today = timezone.localdate()
    from_d  = request.GET.get('from_date', str(today.replace(day=1)))
    to_d    = request.GET.get('to_date',   str(today))
    party_id = request.GET.get('party', '')
    download = request.GET.get('download', '')

    challans = Challan.objects.select_related('party', 'bill').filter(pk__isnull=False).order_by('-date')
    # Apply filters only if user has set them
    if from_d:
        challans = challans.filter(date__gte=from_d)
    if to_d:
        challans = challans.filter(date__lte=to_d)
    if party_id:
        challans = challans.filter(party_id=party_id)

    # CSV download
    if download == 'csv':
        response = HttpResponse(content_type='text/csv')
        fname = f'challans_{from_d}_to_{to_d}.csv'
        response['Content-Disposition'] = f'attachment; filename="{fname}"'
        writer = csv.writer(response)
        writer.writerow(['Challan No.', 'Party', 'Date', 'Total Amount', 'Linked Bill', 'Items'])
        for ch in challans:
            items_str = '; '.join([f"{i.product.design_name} x{i.quantity}@{i.price}" for i in ch.items.all()])
            writer.writerow([
                ch.challan_number,
                ch.party.name if ch.party else '',
                ch.date,
                ch.total_amount,
                ch.bill.bill_number if ch.bill else 'Manual',
                items_str,
            ])
        return response

    parties = Party.objects.all()
    total_amount = challans.aggregate(t=Sum('total_amount'))['t'] or 0
    return render(request, 'admin/challan_list.html', {
        'challans': challans, 'parties': parties,
        'from_date': from_d, 'to_date': to_d,
        'sel_party': party_id, 'total_amount': total_amount,
    })


@adm_required
def challan_create(request):
    """Manually create challan (not linked to any bill)."""
    parties = Party.objects.all()
    products = Product.objects.all()
    if request.method == 'POST':
        try:
            ch = Challan.objects.create(
                challan_number=request.POST['challan_number'],
                party_id=request.POST['party'],
                date=request.POST['date'],
                notes=request.POST.get('notes', '')
            )
            pids = request.POST.getlist('product_id[]')
            qtys = request.POST.getlist('quantity[]')
            prices = request.POST.getlist('price[]')
            total = Decimal('0')
            for pid, qty, price in zip(pids, qtys, prices):
                if pid and qty and Decimal(qty) > 0:
                    prod = Product.objects.get(pk=pid)
                    p = Decimal(price) if price else prod.challan_price
                    t = Decimal(qty) * p
                    total += t
                    ChallanItem.objects.create(challan=ch, product=prod, quantity=qty, price=p, total=t)
            ch.total_amount = total
            ch.save()
            messages.success(request, f'Challan #{ch.challan_number} created!')
            return redirect('challan_detail', pk=ch.pk)
        except Exception as e:
            messages.error(request, f'Error: {e}')
    return render(request, 'admin/challan_form.html', {'parties': parties, 'products': products, 'title': 'Create Challan', 'obj': None})


@adm_required
def challan_edit(request, pk):
    """Edit challan (both auto-generated and manual). Price is editable."""
    ch = get_object_or_404(Challan, pk=pk)
    parties = Party.objects.all()
    products = Product.objects.all()
    if request.method == 'POST':
        try:
            ch.challan_number = request.POST['challan_number']
            ch.party_id = request.POST['party']
            ch.date = request.POST['date']
            ch.notes = request.POST.get('notes', '')
            ch.items.all().delete()
            pids = request.POST.getlist('product_id[]')
            qtys = request.POST.getlist('quantity[]')
            prices = request.POST.getlist('price[]')
            total = Decimal('0')
            for pid, qty, price in zip(pids, qtys, prices):
                if pid and qty and Decimal(qty) > 0:
                    prod = Product.objects.get(pk=pid)
                    p = Decimal(price) if price else prod.challan_price
                    t = Decimal(qty) * p
                    total += t
                    ChallanItem.objects.create(challan=ch, product=prod, quantity=qty, price=p, total=t)
            ch.total_amount = total
            ch.save()
            messages.success(request, 'Challan updated!')
            return redirect('challan_detail', pk=ch.pk)
        except Exception as e:
            messages.error(request, f'Error: {e}')
    return render(request, 'admin/challan_form.html', {'parties': parties, 'products': products, 'title': 'Edit Challan', 'obj': ch})


@adm_required
def challan_detail(request, pk):
    ch = get_object_or_404(Challan, pk=pk)
    return render(request, 'admin/challan_detail.html', {'ch': ch})


@adm_required
def challan_delete(request, pk):
    ch = get_object_or_404(Challan, pk=pk)
    if request.method == 'POST':
        ch.delete(); messages.success(request, 'Challan deleted!')
        return redirect('challan_list')
    return render(request, 'admin/confirm_delete.html', {'obj': ch, 'back': 'challan_list'})


# ── EXPENSE ───────────────────────────────────────────────────────────────────

@adm_required
def expense_list(request):
    expenses = Expense.objects.all()
    total = expenses.aggregate(t=Sum('amount'))['t'] or 0
    return render(request, 'admin/expense_list.html', {'expenses': expenses, 'total': total})


@adm_required
def expense_add(request):
    if request.method == 'POST':
        try:
            Expense.objects.create(category=request.POST['category'], amount=request.POST['amount'], date=request.POST['date'], description=request.POST.get('description', ''))
            messages.success(request, 'Expense added!')
            return redirect('expense_list')
        except Exception as e:
            messages.error(request, f'Error: {e}')
    return render(request, 'admin/expense_form.html', {'cats': Expense.CATEGORY_CHOICES})


@adm_required
def expense_delete(request, pk):
    e = get_object_or_404(Expense, pk=pk)
    if request.method == 'POST':
        e.delete(); messages.success(request, 'Expense deleted!')
        return redirect('expense_list')
    return render(request, 'admin/confirm_delete.html', {'obj': e, 'back': 'expense_list'})


# ── REPORTS ───────────────────────────────────────────────────────────────────

@adm_required
def production_report(request):
    from_d = request.GET.get('from_date', str(timezone.localdate().replace(day=1)))
    to_d   = request.GET.get('to_date',   str(timezone.localdate()))
    prods  = Production.objects.filter(date__gte=from_d, date__lte=to_d).select_related('design__machine','work_entry__attendance__employee').order_by('-date')
    total  = prods.aggregate(t=Sum('mts_produced'))['t'] or 0
    by_design = prods.values('design__design_name','design__machine__machine_number').annotate(total=Sum('mts_produced')).order_by('-total')
    return render(request, 'admin/production_report.html', {'prods': prods[:200], 'total': total, 'by_design': by_design, 'from_date': from_d, 'to_date': to_d})



@adm_required
def salary_report(request):
    """Shows salary report with Pay Salary button per employee."""
    today = timezone.localdate()
    month = int(request.GET.get('month', today.month))
    year  = int(request.GET.get('year',  today.year))
    rows  = []
    for emp in Employee.objects.filter(is_active=True):
        h = Attendance.objects.filter(
            employee=emp, date__month=month, date__year=year
        ).aggregate(h=Sum('total_hours'))['h'] or Decimal('0')
        gross = Decimal(str(h)) * emp.salary_per_hour

        # Pending (undeducted) advances
        pending_advances = Advance.objects.filter(employee=emp, is_deducted=False).order_by('date')
        total_adv = pending_advances.aggregate(t=Sum('amount'))['t'] or Decimal('0')
        net = gross - total_adv

        # Already paid this month?
        paid = SalaryPayment.objects.filter(employee=emp, month=month, year=year).first()

        rows.append({
            'emp': emp, 'hours': h, 'gross': gross,
            'advance': total_adv, 'net': net,
            'paid': paid,
        })
    return render(request, 'admin/salary_report.html', {
        'rows': rows, 'month': month, 'year': year, 'months': range(1, 13)
    })


@adm_required
def salary_pay(request, emp_id):
    """Pay salary to one employee — auto-deducts advances."""
    emp   = get_object_or_404(Employee, pk=emp_id)
    today = timezone.localdate()
    month = int(request.POST.get('month', today.month))
    year  = int(request.POST.get('year',  today.year))

    # Calculate gross from attendance
    h = Attendance.objects.filter(
        employee=emp, date__month=month, date__year=year
    ).aggregate(h=Sum('total_hours'))['h'] or Decimal('0')
    gross = Decimal(str(h)) * emp.salary_per_hour

    # All pending advances
    pending_advances = list(Advance.objects.filter(employee=emp, is_deducted=False).order_by('date'))
    total_adv = sum(a.amount for a in pending_advances)
    net = gross - Decimal(str(total_adv))

    amount_paid = Decimal(request.POST.get('amount_paid', str(max(net, Decimal('0')))))

    if request.method == 'POST':
        try:
            # Create salary payment record
            payment = SalaryPayment.objects.create(
                employee=emp,
                month=month,
                year=year,
                total_hours=h,
                gross_salary=gross,
                advance_deducted=Decimal(str(total_adv)),
                amount_paid=amount_paid,
                net_salary=net,
                payment_date=request.POST.get('payment_date', str(today)),
                note=request.POST.get('note', ''),
            )

            # Mark advances as deducted based on how much was paid
            # Logic: advance is "completed" when gross salary covers it
            # If gross >= total advance → all advances marked deducted
            # If gross < total advance → mark advances starting from oldest until covered
            remaining = gross
            for adv in pending_advances:
                if remaining >= adv.amount:
                    adv.is_deducted = True
                    adv.save()
                    remaining -= adv.amount
                else:
                    break  # Can't cover this advance yet

            messages.success(request, f'Salary paid to {emp.name}! ₹{amount_paid} paid, ₹{total_adv} advance deducted.')
        except Exception as e:
            messages.error(request, f'Error: {e}')

    return redirect(f'/admin/salary/?month={month}&year={year}')


@adm_required
def salary_payment_list(request):
    """Full history of all salary payments made."""
    payments = SalaryPayment.objects.select_related('employee').order_by('-year', '-month', '-payment_date')
    return render(request, 'admin/salary_payment_list.html', {'payments': payments})


@adm_required
def salary_payment_delete(request, pk):
    pay = get_object_or_404(SalaryPayment, pk=pk)
    if request.method == 'POST':
        pay.delete()
        messages.success(request, 'Payment record deleted.')
        return redirect('salary_payment_list')
    return render(request, 'admin/confirm_delete.html', {'obj': pay, 'back': 'salary_payment_list'})


@adm_required
def attendance_report(request):
    today = timezone.localdate()
    from_d = request.GET.get('from_date', str(today.replace(day=1)))
    to_d   = request.GET.get('to_date',   str(today))
    emp_id = request.GET.get('employee', '')
    atts = Attendance.objects.filter(date__gte=from_d, date__lte=to_d).select_related('employee','work_entry')
    if emp_id:
        atts = atts.filter(employee_id=emp_id)
    atts = atts.order_by('-date', 'employee__name')
    emps = Employee.objects.filter(is_active=True)
    return render(request, 'admin/attendance_report.html', {'atts': atts, 'emps': emps, 'from_date': from_d, 'to_date': to_d, 'sel_emp': emp_id})


@adm_required
def inventory(request):
    rows = []
    for prod in Product.objects.all():
        designs = Design.objects.filter(design_name__iexact=prod.design_name)
        produced = sum(
            Production.objects.filter(design=d).aggregate(t=Sum('mts_produced'))['t'] or 0
            for d in designs
        )
        sold = BillItem.objects.filter(product=prod).aggregate(t=Sum('quantity'))['t'] or 0
        rows.append({'product': prod, 'produced': produced, 'sold': sold, 'stock': Decimal(str(produced)) - Decimal(str(sold))})
    return render(request, 'admin/inventory.html', {'rows': rows})


# ── API: product price lookup ─────────────────────────────────────────────────

def product_prices(request, pk):
    p = get_object_or_404(Product, pk=pk)
    return JsonResponse({
        'billing_price': str(p.billing_price),
        'challan_price': str(p.challan_price),
        'gst_percent': str(p.gst_percent),
    })


def _rebuild_challan_from_bill(bill):
    ch = None
    # Safely get or create challan — handle all possible exceptions
    try:
        ch = bill.challan
        if not ch.pk:
            ch = None
    except Exception:
        ch = None

    if ch is None:
        # Check if a challan already exists with the same number (avoid duplicate)
        ch = Challan.objects.filter(challan_number=bill.bill_number).first()
        if ch is None:
            ch = Challan.objects.create(
                bill=bill,
                challan_number=bill.bill_number,
                party=bill.party,
                date=bill.date,
            )
        else:
            # Link it to this bill if not already linked
            if ch.bill_id != bill.pk:
                ch.bill = bill

    ch.items.all().delete()
    ch.party = bill.party
    ch.date  = bill.date
    total = Decimal('0')
    for item in bill.items.all():
        t = item.quantity * item.product.challan_price
        total += t
        ChallanItem.objects.create(
            challan=ch, product=item.product,
            quantity=item.quantity,
            price=item.product.challan_price, total=t
        )
    ch.total_amount = total
    ch.save()
    return ch


# ─────────────────────────────────────────────────────────
# AMOUNT IN WORDS helper
# ─────────────────────────────────────────────────────────
def _amount_in_words(amount):
    """Convert number to Indian-style words. e.g. 17640 → Seventeen Thousand Six Hundred Forty Rupees Only"""
    ones = ['','One','Two','Three','Four','Five','Six','Seven','Eight','Nine',
            'Ten','Eleven','Twelve','Thirteen','Fourteen','Fifteen','Sixteen',
            'Seventeen','Eighteen','Nineteen']
    tens_w = ['','','Twenty','Thirty','Forty','Fifty','Sixty','Seventy','Eighty','Ninety']

    def two_digits(n):
        if n < 20: return ones[n]
        return tens_w[n//10] + (' ' + ones[n%10] if n%10 else '')

    def three_digits(n):
        if n >= 100:
            return ones[n//100] + ' Hundred' + (' ' + two_digits(n%100) if n%100 else '')
        return two_digits(n)

    n = int(amount)
    if n == 0: return 'Zero Rupees Only'
    parts = []
    if n >= 10000000:
        parts.append(three_digits(n // 10000000) + ' Crore'); n %= 10000000
    if n >= 100000:
        parts.append(three_digits(n // 100000) + ' Lakh'); n %= 100000
    if n >= 1000:
        parts.append(three_digits(n // 1000) + ' Thousand'); n %= 1000
    if n > 0:
        parts.append(three_digits(n))
    return ' '.join(parts) + ' Rupees Only'


@adm_required
def company_profile(request):
    from .models import CompanyProfile
    company = CompanyProfile.objects.first()
    if request.method == 'POST':
        if not company:
            company = CompanyProfile()
        company.name    = request.POST.get('name', '')
        company.address = request.POST.get('address', '')
        company.gstin   = request.POST.get('gstin', '')
        company.phone   = request.POST.get('phone', '')
        company.email   = request.POST.get('email', '')
        company.terms   = request.POST.get('terms', '')
        if request.FILES.get('logo'):
            company.logo = request.FILES['logo']
        company.save()
        messages.success(request, 'Company profile saved!')
        return redirect('company_profile')
    return render(request, 'admin/company_profile.html', {'company': company})









# @adm_required
# def bill_create(request):
#     parties = Party.objects.all()
#     products = Product.objects.all()
#     today = date.today()
#     if request.method == 'POST':
#         try:
#             apply_gst = request.POST.get('apply_gst') == 'on'
#             is_igst   = request.POST.get('is_igst') == 'on'
#             bill = Bill.objects.create(
#                 bill_number=request.POST['bill_number'],
#                 party_id=request.POST['party'],
#                 date=request.POST['date'],
#                 apply_gst=apply_gst,
#                 is_igst=is_igst,
#                 notes=request.POST.get('notes', '')
#             )
#             pids = request.POST.getlist('product_id[]')
#             qtys = request.POST.getlist('quantity[]')
#             subtotal = Decimal('0'); total_gst = Decimal('0')
#             for pid, qty in zip(pids, qtys):
#                 if pid and qty and Decimal(qty) > 0:
#                     prod = Product.objects.get(pk=pid)
#                     base = Decimal(qty) * prod.billing_price
#                     gst_amt = (base * prod.gst_percent / 100).quantize(Decimal('0.01')) if apply_gst and prod.gst_percent > 0 else Decimal('0')
#                     subtotal += base; total_gst += gst_amt
#                     BillItem.objects.create(
#                         bill=bill, product=prod, quantity=qty,
#                         price=prod.billing_price,
#                         hsn_code=prod.hsn_code, unit=prod.unit,
#                         gst_percent=prod.gst_percent if apply_gst else Decimal('0'),
#                         gst_amount=gst_amt, total=base + gst_amt
#                     )
#             bill.subtotal = subtotal; bill.gst_amount = total_gst
#             # Split GST into SGST+CGST or IGST
#             if apply_gst:
#                 if is_igst:
#                     bill.igst_amount = total_gst; bill.sgst_amount = Decimal('0'); bill.cgst_amount = Decimal('0')
#                 else:
#                     half = (total_gst / 2).quantize(Decimal('0.01'))
#                     bill.sgst_amount = half; bill.cgst_amount = total_gst - half; bill.igst_amount = Decimal('0')
#             bill.total_amount = subtotal + total_gst
#             bill.save()
#             _rebuild_challan_from_bill(bill)
#             messages.success(request, f'Bill #{bill.bill_number} created! Challan auto-generated.')
#             return redirect('bill_detail', pk=bill.pk)
#         except Exception as e:
#             messages.error(request, f'Error: {e}')
#     next_num = _next_bill_number()
    
#     return render(request, 'admin/bill_form.html', {'today': today,'parties': parties, 'products': products, 'title': 'Create Bill', 'obj': None, 'next_bill_number': next_num})


# @adm_required
# def bill_edit(request, pk):
#     bill = get_object_or_404(Bill, pk=pk)
#     parties = Party.objects.all()
#     products = Product.objects.all()
#     today = date.today()
#     if request.method == 'POST':
#         try:
#             apply_gst = request.POST.get('apply_gst') == 'on'
#             is_igst   = request.POST.get('is_igst') == 'on'
#             bill.bill_number = request.POST['bill_number']; bill.party_id = request.POST['party']
#             bill.date = request.POST['date']; bill.apply_gst = apply_gst
#             bill.is_igst = is_igst; bill.notes = request.POST.get('notes', '')
#             bill.items.all().delete()
#             pids = request.POST.getlist('product_id[]'); qtys = request.POST.getlist('quantity[]')
#             subtotal = Decimal('0'); total_gst = Decimal('0')
#             for pid, qty in zip(pids, qtys):
#                 if pid and qty and Decimal(qty) > 0:
#                     prod = Product.objects.get(pk=pid)
#                     base = Decimal(qty) * prod.billing_price
#                     gst_amt = (base * prod.gst_percent / 100).quantize(Decimal('0.01')) if apply_gst and prod.gst_percent > 0 else Decimal('0')
#                     subtotal += base; total_gst += gst_amt
#                     BillItem.objects.create(
#                         bill=bill, product=prod, quantity=qty,
#                         price=prod.billing_price,
#                         hsn_code=prod.hsn_code, unit=prod.unit,
#                         gst_percent=prod.gst_percent if apply_gst else Decimal('0'),
#                         gst_amount=gst_amt, total=base + gst_amt
#                     )
#             bill.subtotal = subtotal; bill.gst_amount = total_gst
#             if apply_gst:
#                 if is_igst:
#                     bill.igst_amount = total_gst; bill.sgst_amount = Decimal('0'); bill.cgst_amount = Decimal('0')
#                 else:
#                     half = (total_gst / 2).quantize(Decimal('0.01'))
#                     bill.sgst_amount = half; bill.cgst_amount = total_gst - half; bill.igst_amount = Decimal('0')
#             bill.total_amount = subtotal + total_gst
#             bill.save()
#             _rebuild_challan_from_bill(bill)
#             messages.success(request, 'Bill updated! Challan auto-synced.')
#             return redirect('bill_detail', pk=bill.pk)

#         except Exception as e:
#             messages.error(request, f'Error: {e}')
       
#     return render(request, 'admin/bill_form.html', {'obj':bill,'today': today, 'parties': parties, 'products': products, 'title': 'Edit Bill', 'obj': bill})

