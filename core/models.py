from django.db import models
from django.utils import timezone


class Machine(models.Model):
    CATEGORY_CHOICES = [('high_speed', 'High Speed'), ('krochek', 'Krochek')]
    machine_number = models.CharField(max_length=50, unique=True)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    def __str__(self): return f"Machine {self.machine_number}"
    class Meta: ordering = ['machine_number']


class Design(models.Model):
    machine = models.ForeignKey(Machine, on_delete=models.CASCADE, related_name='designs')
    design_name = models.CharField(max_length=100)
    patti_count = models.IntegerField()
    def __str__(self): return f"{self.design_name} (M{self.machine.machine_number})"
    class Meta: ordering = ['design_name']


class Employee(models.Model):
    name = models.CharField(max_length=100)
    user_id = models.CharField(max_length=50, unique=True)
    password = models.CharField(max_length=100)
    machine = models.ForeignKey(Machine, on_delete=models.SET_NULL, null=True, blank=True)
    joining_date = models.DateField()
    salary_per_hour = models.DecimalField(max_digits=8, decimal_places=2)
    is_active = models.BooleanField(default=True)
    def __str__(self): return f"{self.name} ({self.user_id})"
    class Meta: ordering = ['name']


class Attendance(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='attendances')
    date = models.DateField(default=timezone.localdate)
    entry_time = models.DateTimeField(null=True, blank=True)
    exit_time = models.DateTimeField(null=True, blank=True)
    total_hours = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    def __str__(self): return f"{self.employee.name} - {self.date}"
    class Meta: ordering = ['-date', '-entry_time']


class WorkEntry(models.Model):
    SHIFT_CHOICES = [('day', 'Day'), ('night', 'Night')]
    attendance = models.OneToOneField(Attendance, on_delete=models.CASCADE, related_name='work_entry')
    shift = models.CharField(max_length=10, choices=SHIFT_CHOICES, default='day')
    katay = models.IntegerField()
    mts_per_katay = models.DecimalField(max_digits=8, decimal_places=2)
    total_mts = models.DecimalField(max_digits=10, decimal_places=2)
    def __str__(self): return f"WorkEntry-{self.attendance}"


class Production(models.Model):
    work_entry = models.ForeignKey(WorkEntry, on_delete=models.CASCADE, related_name='productions')
    design = models.ForeignKey(Design, on_delete=models.CASCADE)
    mts_produced = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateField(default=timezone.localdate)
    def __str__(self): return f"{self.design.design_name} - {self.mts_produced} MTS"
    class Meta: ordering = ['-date']


class Advance(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='advances')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateField()
    is_deducted = models.BooleanField(default=False)
    note = models.TextField(blank=True)
    def __str__(self): return f"{self.employee.name} - ₹{self.amount}"
    class Meta: ordering = ['-date']


class SalaryPayment(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='salary_payments')
    month = models.IntegerField()
    year = models.IntegerField()
    total_hours = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    gross_salary = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    advance_deducted = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    net_salary = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    payment_date = models.DateField(default=timezone.localdate)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self): return f"{self.employee.name} - {self.month}/{self.year} - ₹{self.amount_paid}"
    class Meta: ordering = ['-year', '-month']


class Salary(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='salaries')
    month = models.IntegerField()
    year = models.IntegerField()
    total_hours = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    gross_salary = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    advance_deducted = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    net_salary = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self): return f"{self.employee.name} - {self.month}/{self.year}"
    class Meta: unique_together = ['employee', 'month', 'year']; ordering = ['-year', '-month']


# ── Company Profile ── (single row — your business details for invoice header)
class CompanyProfile(models.Model):
    name         = models.CharField(max_length=200, default='Shree Mahalaxmi Lace')
    address      = models.TextField(default='142, Divyanand Society, U.M Road, Near Chosath Jogani Mandir, Surat')
    gstin        = models.CharField(max_length=20, default='24AGQPJ2786A1ZF')
    phone        = models.CharField(max_length=20, default='9825033599')
    email        = models.EmailField(blank=True, default='shreemahalaxmilace@gmail.com')
    logo         = models.ImageField(upload_to='company/', null=True, blank=True)
    terms        = models.TextField(blank=True, default='Goods once sold will not be taken back.')
    def __str__(self): return self.name
    class Meta: verbose_name = 'Company Profile'


class Party(models.Model):
    name        = models.CharField(max_length=200)
    gst_number  = models.CharField(max_length=20, blank=True)
    address     = models.TextField(blank=True)
    phone       = models.CharField(max_length=15, blank=True)
    email       = models.EmailField(blank=True)
    def __str__(self): return self.name
    class Meta: ordering = ['name']; verbose_name_plural = "Parties"


class Product(models.Model):
    UNIT_CHOICES = [('PCS','PCS'),('MTR','MTR'),('KG','KG'),('SET','SET'),('BOX','BOX'),('NOS','NOS')]
    design_name          = models.CharField(max_length=100)
    hsn_code             = models.CharField(max_length=20, blank=True, help_text='HSN/SAC code e.g. 5806')
    unit                 = models.CharField(max_length=10, choices=UNIT_CHOICES, default='MTR')
    manufacturing_price  = models.DecimalField(max_digits=10, decimal_places=2)
    billing_price        = models.DecimalField(max_digits=10, decimal_places=2)
    challan_price        = models.DecimalField(max_digits=10, decimal_places=2)
    gst_percent          = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    def __str__(self): return self.design_name
    class Meta: ordering = ['design_name']


class Bill(models.Model):
    bill_number   = models.CharField(max_length=50, unique=True)
    party         = models.ForeignKey(Party, on_delete=models.PROTECT, null=True, blank=True)
    date          = models.DateField(default=timezone.localdate)
    apply_gst     = models.BooleanField(default=False)
    is_igst       = models.BooleanField(default=False, help_text='Inter-state = IGST; Intra-state = SGST+CGST')
    subtotal      = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount      = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    sgst_amount   = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    cgst_amount   = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    igst_amount   = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    gst_amount    = models.DecimalField(max_digits=12, decimal_places=2, default=0)  # total GST
    total_amount  = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes         = models.TextField(blank=True)
    created_at    = models.DateTimeField(auto_now_add=True)
    def __str__(self): return f"Bill #{self.bill_number} - {self.party}"
    class Meta: ordering = ['-date']


class BillItem(models.Model):
    bill        = models.ForeignKey(Bill, on_delete=models.CASCADE, related_name='items')
    product     = models.ForeignKey(Product, on_delete=models.PROTECT)
    hsn_code    = models.CharField(max_length=20, blank=True)   # copied from product
    unit        = models.CharField(max_length=10, default='MTR')# copied from product
    quantity    = models.DecimalField(max_digits=10, decimal_places=2)
    price       = models.DecimalField(max_digits=10, decimal_places=2)
    gst_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    gst_amount  = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total       = models.DecimalField(max_digits=12, decimal_places=2)
    def __str__(self): return f"{self.product.design_name} x {self.quantity}"


class Challan(models.Model):
    bill           = models.OneToOneField(Bill, on_delete=models.SET_NULL, null=True, blank=True, related_name='challan')
    challan_number = models.CharField(max_length=50, unique=True)
    party          = models.ForeignKey(Party, on_delete=models.PROTECT, null=True, blank=True)
    date           = models.DateField(default=timezone.localdate)
    total_amount   = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes          = models.TextField(blank=True)
    def __str__(self): return f"Challan #{self.challan_number}"
    class Meta: ordering = ['-date']


class ChallanItem(models.Model):
    challan  = models.ForeignKey(Challan, on_delete=models.CASCADE, related_name='items')
    product  = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    price    = models.DecimalField(max_digits=10, decimal_places=2)
    total    = models.DecimalField(max_digits=12, decimal_places=2)
    def __str__(self): return f"{self.product.design_name} x {self.quantity}"


class Expense(models.Model):
    CATEGORY_CHOICES = [('light','Light Bill'),('salary','Salary'),('rent','Rent'),('other','Other')]
    category    = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    amount      = models.DecimalField(max_digits=10, decimal_places=2)
    date        = models.DateField()
    description = models.TextField(blank=True)
    def __str__(self): return f"{self.get_category_display()} - ₹{self.amount}"
    class Meta: ordering = ['-date']
