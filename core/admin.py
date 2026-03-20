from django.contrib import admin
from .models import (Employee, Machine, Design, Attendance, WorkEntry,
                     Production, Advance, Salary, Party, Product,
                     Bill, BillItem, Challan, ChallanItem, Expense)

admin.site.register(Employee)
admin.site.register(Machine)
admin.site.register(Design)
admin.site.register(Attendance)
admin.site.register(WorkEntry)
admin.site.register(Production)
admin.site.register(Advance)
admin.site.register(Salary)
admin.site.register(Party)
admin.site.register(Product)
admin.site.register(Bill)
admin.site.register(BillItem)
admin.site.register(Challan)
admin.site.register(ChallanItem)
admin.site.register(Expense)
