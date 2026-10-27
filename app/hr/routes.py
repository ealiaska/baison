from datetime import date, datetime, time, timedelta

from flask import Blueprint, flash, redirect, render_template, request, url_for

from .. import db
from .. import models as m
from ..auth import role_required

hr_bp = Blueprint("hr", __name__)

LATE_GRACE = timedelta(minutes=15)  # допуск к смене, мин


def _parse_hhmm(value, fallback):
    try:
        return time.fromisoformat(value)
    except (ValueError, TypeError):
        return fallback


def _planned(emp, day):
    return datetime.combine(day, _parse_hhmm(emp.shift_start, time(9, 0)))


def _planned_end(emp, day):
    return datetime.combine(day, _parse_hhmm(emp.shift_end, time(18, 0)))


@hr_bp.route("/")
@role_required(m.ROLE_ADMIN, m.ROLE_MANAGER)
def index():
    today = date.today()
    employees = m.Employee.query.filter_by(is_active=True).order_by(m.Employee.name).all()

    # сегодня: отметки по каждому сотруднику
    today_rows = []
    for emp in employees:
        rec = m.Attendance.query.filter_by(employee_id=emp.id, date=today).first()
        if rec and rec.actual_start is not None:
            state = rec.status  # on_time / late
            finished = rec.actual_end is not None
            arrived = rec.actual_start.strftime("%H:%M")
            left = rec.actual_end.strftime("%H:%M") if rec.actual_end else ""
        else:
            state = "planned"
            finished = False
            arrived = ""
            left = ""
        today_rows.append({
            "emp": emp, "rec": rec, "state": state,
            "finished": finished, "arrived": arrived, "left": left,
        })

    # отчёт за последние 7 дней
    days = [today - timedelta(days=i) for i in range(6, -1, -1)]
    by_emp = {
        emp.id: {
            r.date: r for r in
            m.Attendance.query.filter(m.Attendance.employee_id == emp.id).all()
        }
        for emp in employees
    }
    report_rows = []
    for emp in employees:
        cells = []
        late = absent = 0
        for d in days:
            rec = by_emp[emp.id].get(d)
            if rec and rec.actual_start is not None:
                mark = "L" if rec.status == "late" else "O"
                if rec.status == "late":
                    late += 1
            elif d < today and emp.works_on(d.weekday()):
                mark = "A"
                absent += 1
            else:
                mark = ""
            cells.append((d, mark))
        report_rows.append({"emp": emp, "cells": cells, "late": late, "absent": absent})

    return render_template(
        "hr/index.html",
        today_rows=today_rows,
        employees=m.Employee.query.order_by(m.Employee.name).all(),
        days=days,
        report_rows=report_rows,
        today=today,
    )


@hr_bp.route("/employees/add", methods=["POST"])
@role_required(m.ROLE_ADMIN, m.ROLE_MANAGER)
def employee_add():
    name = request.form.get("name", "").strip()
    if not name:
        flash("Имя обязательно", "error")
        return redirect(url_for("hr.index"))
    db.session.add(m.Employee(
        name=name,
        position=request.form.get("position", "").strip(),
        shift_start=request.form.get("shift_start", "09:00").strip() or "09:00",
        shift_end=request.form.get("shift_end", "18:00").strip() or "18:00",
        work_days=(request.form.get("work_days", "1111110") or "1111110")[:7].ljust(7, "0"),
        phone=request.form.get("phone", "").strip(),
    ))
    db.session.commit()
    flash("Сотрудник добавлен", "success")
    return redirect(url_for("hr.index"))


@hr_bp.route("/employees/<int:employee_id>/toggle", methods=["POST"])
@role_required(m.ROLE_ADMIN, m.ROLE_MANAGER)
def employee_toggle(employee_id):
    emp = m.Employee.query.get_or_404(employee_id)
    emp.is_active = not emp.is_active
    db.session.commit()
    flash("Статус изменён", "success")
    return redirect(url_for("hr.index"))


def _get_or_create(employee_id):
    emp = m.Employee.query.get_or_404(employee_id)
    today = date.today()
    rec = m.Attendance.query.filter_by(employee_id=emp.id, date=today).first()
    if rec is None:
        rec = m.Attendance(
            employee_id=emp.id, date=today,
            planned_start=_planned(emp, today),
            planned_end=_planned_end(emp, today),
            status="planned",
        )
        db.session.add(rec)
        db.session.flush()
    return emp, rec


@hr_bp.route("/attendance/<int:employee_id>/in", methods=["POST"])
@role_required(m.ROLE_ADMIN, m.ROLE_MANAGER)
def punch_in(employee_id):
    emp, rec = _get_or_create(employee_id)
    now = datetime.now()
    rec.actual_start = now
    rec.status = "late" if now > rec.planned_start + LATE_GRACE else "on_time"
    db.session.commit()
    mark = "опоздание" if rec.status == "late" else "вовремя"
    flash(f"{emp.name}: отметка прихода {now.strftime('%H:%M')} ({mark})", "success")
    return redirect(request.form.get("next") or url_for("hr.index"))


@hr_bp.route("/attendance/<int:employee_id>/out", methods=["POST"])
@role_required(m.ROLE_ADMIN, m.ROLE_MANAGER)
def punch_out(employee_id):
    emp, rec = _get_or_create(employee_id)
    if rec.actual_start is None:
        flash("Сначала отметьте приход", "error")
        return redirect(url_for("hr.index"))
    rec.actual_end = datetime.now()
    db.session.commit()
    flash(f"{emp.name}: отметка ухода {rec.actual_end.strftime('%H:%M')}", "success")
    return redirect(request.form.get("next") or url_for("hr.index"))
