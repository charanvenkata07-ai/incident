import asyncio
import os
import sys
from sqlalchemy import select

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.core.database import async_session_maker
from app.core.security import hash_password
from app.models.user import User
from app.models.employee import Employee

async def migrate_admin_account():
    print("Starting Admin Account and Employee Disassociation Migration...")
    async with async_session_maker() as session:
        # 1. Search for any user with email pvcharan975@gmail.com
        res = await session.execute(select(User).where(User.email.ilike("pvcharan975@gmail.com")))
        existing_users = res.scalars().all()

        for u in existing_users:
            if u.role == "EMPLOYEE":
                print(f"Found employee user with pvcharan975@gmail.com (id={u.id}). Disassociating and archiving...")
                # Disassociate linked employee
                emp_res = await session.execute(select(Employee).where(Employee.user_id == u.id))
                emp = emp_res.scalar_one_or_none()
                if emp:
                    emp.availability_status = "OFFLINE"
                    emp.is_present = False
                    emp.team_id = None
                    print(f"  Employee {emp.id} marked OFFLINE, not present, team removed.")

                # Rename employee user email and deactivate
                u.email = f"pvcharan975_archived_emp_{u.id.hex[:6]}@incidentflow.dev"
                u.is_active = False
                print(f"  User {u.id} archived with email {u.email} and is_active=False.")
                await session.flush()

        # 2. Check for existing admin user
        admin_res = await session.execute(select(User).where(User.email == "pvcharan975@gmail.com"))
        admin_user = admin_res.scalar_one_or_none()

        admin_pwd_hash = hash_password("pvcharan12345PV")

        if admin_user:
            print(f"Admin user pvcharan975@gmail.com already exists (id={admin_user.id}). Updating password and role...")
            admin_user.role = "ADMIN"
            admin_user.is_active = True
            admin_user.hashed_password = admin_pwd_hash
        else:
            # Check if there is an admin@incidentflow.dev we can promote or create new
            legacy_admin_res = await session.execute(select(User).where(User.email == "admin@incidentflow.dev"))
            legacy_admin = legacy_admin_res.scalar_one_or_none()

            # We create pvcharan975@gmail.com as the canonical ADMIN
            new_admin = User(
                email="pvcharan975@gmail.com",
                hashed_password=admin_pwd_hash,
                full_name="Administrator (pvcharan975)",
                role="ADMIN",
                is_active=True
            )
            session.add(new_admin)
            print("Created canonical Admin account: pvcharan975@gmail.com")

            # Also ensure legacy admin has the admin password if present
            if legacy_admin:
                legacy_admin.hashed_password = admin_pwd_hash

        await session.commit()
        print("Admin account migration successfully committed!")

        # Verification query
        all_pv = (await session.execute(select(User).where(User.email.ilike("%pvcharan975%")))).scalars().all()
        print("\nVerification of accounts matching pvcharan975:")
        for u in all_pv:
            print(f"  User id={u.id}, email={u.email}, role={u.role}, is_active={u.is_active}")

if __name__ == "__main__":
    asyncio.run(migrate_admin_account())
