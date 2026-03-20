from django.contrib import admin as django_admin
from django.urls import path
from core import views as v
# from lace_erp import settings
from django.conf.urls.static import static
from django.conf import settings

urlpatterns = [
    path('django-admin/', django_admin.site.urls),
    # Employee
    path('',             v.emp_login,     name='emp_login'),
    path('logout/',      v.emp_logout,    name='emp_logout'),
    path('dashboard/',   v.emp_dashboard, name='emp_dashboard'),
    path('entry/',       v.mark_entry,    name='mark_entry'),
    path('exit/',        v.mark_exit,     name='mark_exit'),
    path('history/',     v.emp_history,   name='emp_history'),
    # Admin auth
    path('admin/login/',     v.adm_login,    name='adm_login'),
    path('admin/logout/',    v.adm_logout,   name='adm_logout'),
    path('admin/dashboard/', v.adm_dashboard,name='adm_dashboard'),
    # Employees
    path('admin/employees/',                     v.emp_list,    name='emp_list'),
    path('admin/employees/add/',                 v.emp_add,     name='emp_add'),
    path('admin/employees/<int:pk>/edit/',       v.emp_edit,    name='emp_edit'),
    path('admin/employees/<int:pk>/delete/',     v.emp_delete,  name='emp_delete'),
    # Machines
    path('admin/machines/',                      v.machine_list,   name='machine_list'),
    path('admin/machines/add/',                  v.machine_add,    name='machine_add'),
    path('admin/machines/<int:pk>/edit/',        v.machine_edit,   name='machine_edit'),
    path('admin/machines/<int:pk>/delete/',      v.machine_delete, name='machine_delete'),
    # Designs
    path('admin/designs/',                       v.design_list,   name='design_list'),
    path('admin/designs/add/',                   v.design_add,    name='design_add'),
    path('admin/designs/<int:pk>/edit/',         v.design_edit,   name='design_edit'),
    path('admin/designs/<int:pk>/delete/',       v.design_delete, name='design_delete'),
    # Advances
    path('admin/advances/',                      v.advance_list,  name='advance_list'),
    path('admin/advances/add/',                  v.advance_add,   name='advance_add'),
    # Parties
    path('admin/parties/',                       v.party_list,    name='party_list'),
    path('admin/parties/add/',                   v.party_add,     name='party_add'),
    path('admin/parties/<int:pk>/edit/',         v.party_edit,    name='party_edit'),
    path('admin/parties/<int:pk>/delete/',       v.party_delete,  name='party_delete'),
    # Products
    path('admin/products/',                      v.product_list,   name='product_list'),
    path('admin/products/add/',                  v.product_add,    name='product_add'),
    path('admin/products/<int:pk>/edit/',        v.product_edit,   name='product_edit'),
    path('admin/products/<int:pk>/delete/',      v.product_delete, name='product_delete'),
    path('api/product/<int:pk>/prices/',         v.product_prices, name='product_prices'),
    # Bills
    path('admin/bills/',                         v.bill_list,    name='bill_list'),
    path('admin/bills/create/',                  v.bill_create,  name='bill_create'),
    path('admin/bills/<int:pk>/',                v.bill_detail,  name='bill_detail'),
    path('admin/bills/<int:pk>/edit/',           v.bill_edit,    name='bill_edit'),
    path('admin/bills/<int:pk>/delete/',         v.bill_delete,  name='bill_delete'),
    # Challans
    path('admin/challans/',                      v.challan_list,   name='challan_list'),
    path('admin/challans/create/',               v.challan_create, name='challan_create'),
    path('admin/challans/<int:pk>/',             v.challan_detail, name='challan_detail'),
    path('admin/challans/<int:pk>/edit/',        v.challan_edit,   name='challan_edit'),
    path('admin/challans/<int:pk>/delete/',      v.challan_delete, name='challan_delete'),
    # Expenses
    path('admin/expenses/',                      v.expense_list,   name='expense_list'),
    path('admin/expenses/add/',                  v.expense_add,    name='expense_add'),
    path('admin/expenses/<int:pk>/delete/',      v.expense_delete, name='expense_delete'),
    # Salary
    path('admin/salary/',                        v.salary_report,         name='salary_report'),
    path('admin/salary/pay/<int:emp_id>/',       v.salary_pay,            name='salary_pay'),
    path('admin/salary/payments/',               v.salary_payment_list,   name='salary_payment_list'),
    path('admin/salary/payments/<int:pk>/delete/', v.salary_payment_delete, name='salary_payment_delete'),
    # Reports
    path('admin/production/',    v.production_report, name='production_report'),
    path('admin/attendance/',    v.attendance_report, name='attendance_report'),
    path('admin/inventory/',     v.inventory,         name='inventory'),
    path('admin/company-profile/', v.company_profile,   name='company_profile'),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)