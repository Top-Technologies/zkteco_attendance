/** @odoo-module **/
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onMounted, onWillUnmount, useState, useRef } from "@odoo/owl";

class ZKTecoKPIDashboard extends Component {
    static template = "zkteco_attendance.KPIDashboard";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.donutChart = null;
        this.barChart = null;
        this.donutRef = useRef("donutCanvas");
        this.barRef = useRef("barCanvas");

        this.state = useState({
            loading: true,
            today: new Date().toLocaleDateString("en-GB", { weekday: "long", year: "numeric", month: "long", day: "numeric" }),
            totalEmployees: 0,
            presentToday: 0,
            absentToday: 0,
            onLeaveToday: 0,
            missedPunchToday: 0,
            lateArrivalsToday: 0,
            earlyLeavesToday: 0,
            overtimeToday: 0.0,
            attendanceRateToday: 0.0,
            punctualityRate: 0.0,
            weeklyData: [],
            paidLeaveMonth: 0,
            unpaidLeaveMonth: 0,
            totalDevices: 0,
            onlineDevices: 0,
        });

        onMounted(() => this._loadDashboard());
        onWillUnmount(() => this._destroyCharts());
    }

    async _loadDashboard() {
        this.state.loading = true;
        try {
            const [stats, weekly, leaveStats] = await Promise.all([
                this._fetchTodayStats(),
                this._fetchWeeklyStats(),
                this._fetchMonthLeaveStats(),
            ]);

            Object.assign(this.state, stats, { weeklyData: weekly }, leaveStats, { loading: false });

            // Give the DOM a tick to render the canvas elements
            setTimeout(() => {
                this._renderDonutChart();
                this._renderBarChart();
            }, 100);
        } catch (e) {
            console.error("KPI Dashboard load error:", e);
            this.state.loading = false;
        }
    }

    async _fetchTodayStats() {
        const today = new Date().toISOString().slice(0, 10);

        const [allEmployees, records] = await Promise.all([
            this.orm.searchCount("hr.employee", [["active", "=", true]]),
            this.orm.searchRead(
                "zkteco.attendance.record",
                [["date", "=", today]],
                ["status", "is_late", "is_early_leave", "overtime_hours"]
            ),
        ]);

        let deviceStats = { totalDevices: 0, onlineDevices: 0 };
        try {
            const [total, online] = await Promise.all([
                this.orm.searchCount("zkteco.device", []),
                this.orm.searchCount("zkteco.device", [["is_online", "=", true]]),
            ]);
            deviceStats = { totalDevices: total, onlineDevices: online };
        } catch (_) {}

        const present = records.filter((r) => r.status === "present").length;
        const absent = records.filter((r) => r.status === "absent").length;
        const onLeave = records.filter((r) => r.status === "on_leave").length;
        const missed = records.filter((r) => r.status === "missed_punch").length;
        const late = records.filter((r) => r.is_late).length;
        const early = records.filter((r) => r.is_early_leave).length;
        const overtime = records.reduce((s, r) => s + (r.overtime_hours || 0), 0);
        const rate = allEmployees > 0 ? (((present + onLeave) / allEmployees) * 100).toFixed(1) : 0;
        const punct = allEmployees > 0 ? (((present - late) / allEmployees) * 100).toFixed(1) : 0;

        return {
            totalEmployees: allEmployees,
            presentToday: present,
            absentToday: absent,
            onLeaveToday: onLeave,
            missedPunchToday: missed,
            lateArrivalsToday: late,
            earlyLeavesToday: early,
            overtimeToday: overtime.toFixed(1),
            attendanceRateToday: parseFloat(rate),
            punctualityRate: parseFloat(punct),
            ...deviceStats,
        };
    }

    async _fetchWeeklyStats() {
        const today = new Date();
        const days = [];
        const labels = [];
        for (let i = 6; i >= 0; i--) {
            const d = new Date(today);
            d.setDate(today.getDate() - i);
            days.push(d.toISOString().slice(0, 10));
            labels.push(d.toLocaleDateString("en-GB", { weekday: "short", day: "numeric" }));
        }

        const records = await this.orm.readGroup(
            "zkteco.attendance.record",
            [["date", "in", days]],
            ["date", "status"],
            ["date", "status"]
        );

        const presentByDay = {};
        const absentByDay = {};
        days.forEach((d) => { presentByDay[d] = 0; absentByDay[d] = 0; });
        records.forEach((r) => {
            const d = r.date;
            if (r.status === "present" || r.status === "on_leave") presentByDay[d] = (presentByDay[d] || 0) + r.date_count;
            if (r.status === "absent") absentByDay[d] = (absentByDay[d] || 0) + r.date_count;
        });

        return days.map((d, i) => ({
            label: labels[i],
            present: presentByDay[d] || 0,
            absent: absentByDay[d] || 0,
        }));
    }

    async _fetchMonthLeaveStats() {
        const today = new Date();
        const monthStart = new Date(today.getFullYear(), today.getMonth(), 1).toISOString().slice(0, 10);
        const todayStr = today.toISOString().slice(0, 10);

        const records = await this.orm.searchRead(
            "zkteco.attendance.record",
            [["date", ">=", monthStart], ["date", "<=", todayStr], ["status", "=", "on_leave"]],
            ["is_paid_leave", "is_half_day_leave"]
        );

        let paid = 0, unpaid = 0;
        records.forEach((r) => {
            const days = r.is_half_day_leave ? 0.5 : 1.0;
            if (r.is_paid_leave) paid += days;
            else unpaid += days;
        });

        return { paidLeaveMonth: paid.toFixed(1), unpaidLeaveMonth: unpaid.toFixed(1) };
    }

    _destroyCharts() {
        if (this.donutChart) { this.donutChart.destroy(); this.donutChart = null; }
        if (this.barChart) { this.barChart.destroy(); this.barChart = null; }
    }

    _renderDonutChart() {
        const canvas = this.donutRef.el;
        if (!canvas || typeof Chart === "undefined") return;
        if (this.donutChart) this.donutChart.destroy();

        const s = this.state;
        this.donutChart = new Chart(canvas, {
            type: "doughnut",
            data: {
                labels: ["Present", "Absent", "On Leave", "Missed Punch"],
                datasets: [{
                    data: [s.presentToday, s.absentToday, s.onLeaveToday, s.missedPunchToday],
                    backgroundColor: ["#22c55e", "#ef4444", "#3b82f6", "#f59e0b"],
                    borderWidth: 3,
                    borderColor: "#ffffff",
                    hoverOffset: 8,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: "70%",
                plugins: {
                    legend: { position: "bottom", labels: { padding: 16, font: { size: 13 } } },
                    tooltip: { callbacks: { label: (c) => ` ${c.label}: ${c.parsed}` } },
                },
            },
        });
    }

    _renderBarChart() {
        const canvas = this.barRef.el;
        if (!canvas || typeof Chart === "undefined") return;
        if (this.barChart) this.barChart.destroy();

        const labels = this.state.weeklyData.map((d) => d.label);
        const present = this.state.weeklyData.map((d) => d.present);
        const absent = this.state.weeklyData.map((d) => d.absent);

        this.barChart = new Chart(canvas, {
            type: "bar",
            data: {
                labels,
                datasets: [
                    {
                        label: "Present / On Leave",
                        data: present,
                        backgroundColor: "rgba(34, 197, 94, 0.85)",
                        borderRadius: 6,
                        borderSkipped: false,
                    },
                    {
                        label: "Absent",
                        data: absent,
                        backgroundColor: "rgba(239, 68, 68, 0.75)",
                        borderRadius: 6,
                        borderSkipped: false,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: "top" },
                    tooltip: { mode: "index", intersect: false },
                },
                scales: {
                    x: { grid: { display: false }, ticks: { font: { size: 12 } } },
                    y: { beginAtZero: true, grid: { color: "rgba(0,0,0,0.05)" }, ticks: { stepSize: 1 } },
                },
            },
        });
    }

    // Navigation helpers
    _navigate(domain, name) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name,
            res_model: "zkteco.attendance.record",
            view_mode: "list,form",
            views: [[false, "list"], [false, "form"]],
            domain,
            target: "current",
        });
    }

    viewPresent()      { const t = new Date().toISOString().slice(0,10); this._navigate([["date","=",t],["status","=","present"]], "Present Today"); }
    viewAbsent()       { const t = new Date().toISOString().slice(0,10); this._navigate([["date","=",t],["status","=","absent"]], "Absent Today"); }
    viewOnLeave()      { const t = new Date().toISOString().slice(0,10); this._navigate([["date","=",t],["status","=","on_leave"]], "On Leave Today"); }
    viewMissedPunch()  { const t = new Date().toISOString().slice(0,10); this._navigate([["date","=",t],["status","=","missed_punch"]], "Missed Punch Today"); }
    viewLate()         { const t = new Date().toISOString().slice(0,10); this._navigate([["date","=",t],["is_late","=",true]], "Late Arrivals Today"); }
    viewEarlyLeave()   { const t = new Date().toISOString().slice(0,10); this._navigate([["date","=",t],["is_early_leave","=",true]], "Early Departures Today"); }
    viewMonthly()      { this.action.doAction({ type: "ir.actions.act_window", name: "Monthly Summary", res_model: "zkteco.monthly.attendance.summary", view_mode: "list,pivot", views: [[false, "list"], [false, "pivot"]], target: "current" }); }
    viewPayroll()      { this.action.doAction({ type: "ir.actions.act_window", name: "Payroll Summary", res_model: "zkteco.payroll.attendance.summary", view_mode: "list,pivot", views: [[false, "list"], [false, "pivot"]], target: "current" }); }

    async refresh() {
        this._destroyCharts();
        await this._loadDashboard();
    }
}

registry.category("actions").add("zkteco_kpi_dashboard", ZKTecoKPIDashboard);
