# Lace ERP — Setup & Deployment Guide

## Requirements
- Python 3.10+
- MySQL 8.0+
- pip

## Step 1 — Install dependencies
```bash
pip install django mysqlclient
```

## Step 2 — Create MySQL database
```sql
CREATE DATABASE lace_erp CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'lace_user'@'localhost' IDENTIFIED BY 'YourPassword123';
GRANT ALL PRIVILEGES ON lace_erp.* TO 'lace_user'@'localhost';
FLUSH PRIVILEGES;
```

## Step 3 — Configure database
Edit `lace_erp/settings.py`:
```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'lace_erp',
        'USER': 'lace_user',
        'PASSWORD': 'YourPassword123',
        'HOST': 'localhost',
        'PORT': '3306',
    }
}
```

## Step 4 — Run migrations (creates all tables)
```bash
python manage.py makemigrations
python manage.py migrate
```

## Step 5 — Start server
```bash
python manage.py runserver 0.0.0.0:8000
```

## Access the system
- Employee Login:  http://yourserver:8000/
- Admin Login:     http://yourserver:8000/admin/login/
  - Username: admin  |  Password: admin123

## First-time Setup (Admin)
1. Go to Machines → Add Machine (e.g. M1, High Speed)
2. Go to Designs → Add Design (assign to machine, set patti count)
3. Go to Employees → Add Employee (set machine, salary/hour, create User ID + password)
4. Go to Parties → Add customer parties
5. Go to Products → Add products (set billing & challan prices)
6. Done! Employees can now login and mark attendance.

## Key Business Rules
### Time Rounding
| Minutes worked | Rounded to |
|---|---|
| < 15 min  | 0 (ignored) |
| 15–29 min | +0.5 hour  |
| ≥ 30 min  | +1.0 hour  |

### Multi-Design MTS Split
When a machine has multiple designs, total MTS is split proportionally by patti count.

Example: Machine M1 has Design A (5 patti) + Design B (10 patti) = 15 total
- Employee enters 2 Katay × 24 MTS = 48 total MTS
- Design A gets: (5/15) × 48 = **16 MTS**
- Design B gets: (10/15) × 48 = **32 MTS**

### Bill → Challan Auto-Sync
- Creating a bill → challan auto-generated with challan prices
- Editing bill products/quantities → challan items auto-synced
- Challan price is always **independently editable**
- You can also create manual challans (not linked to any bill)

### Salary Calculation
Net Salary = (Total Hours × Rate/Hour) − Pending Advances
