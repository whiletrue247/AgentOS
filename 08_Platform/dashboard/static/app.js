// platform/dashboard/static/app.js

document.addEventListener('DOMContentLoaded', () => {
    // Basic Navigation
    const navLinks = document.querySelectorAll('.nav-links li');
    const views = document.querySelectorAll('.view');

    navLinks.forEach(link => {
        link.addEventListener('click', () => {
            navLinks.forEach(n => n.classList.remove('active'));
            link.classList.add('active');

            const targetId = `view-${link.dataset.target}`;
            views.forEach(v => {
                v.classList.remove('active');
                if (v.id === targetId) {
                    v.classList.add('active');
                }
            });

            if (link.dataset.target === 'tasks') {
                refreshTasks();
            }
        });
    });

    // Setup SSE connection
    setupSSE();

    // Initial fetch
    fetchCost();
});

function setupSSE() {
    const statusText = document.getElementById('sys-status-text');
    const indicator = document.querySelector('.status-indicator');
    const liveFeed = document.getElementById('live-feed');
    let eventCount = 0;

    const eventSource = new EventSource('/api/stream');

    eventSource.onopen = () => {
        statusText.textContent = 'Connected';
        indicator.classList.add('online');
    };

    eventSource.onerror = (err) => {
        statusText.textContent = 'Disconnected';
        indicator.classList.remove('online');
        console.error("SSE Error:", err);
    };

    eventSource.addEventListener('engine_event', (e) => {
        const data = JSON.parse(e.data);
        appendLog(`[${data.type.toUpperCase()}] ${JSON.stringify(data.payload).substring(0, 100)}...`, data.type);

        // Update events count
        eventCount++;
        document.getElementById('stat-events').textContent = eventCount;

        if (data.type === 'budget_warning' || data.type === 'task_complete') {
            fetchCost();
        }
    });

    eventSource.addEventListener('ping', () => {
        console.log("Ping received");
    });

    function appendLog(message, type) {
        const entry = document.createElement('div');
        entry.className = `feed-entry ${type}`;

        const timestamp = new Date().toLocaleTimeString();
        entry.textContent = `[${timestamp}] ${message}`;

        liveFeed.prepend(entry);

        // Keep only last 50
        while (liveFeed.children.length > 50) {
            liveFeed.lastChild.remove();
        }
    }
}

async function fetchCost() {
    try {
        const res = await fetch('/api/cost');
        if (!res.ok) return;
        const data = await res.json();
        const r = data.cost_report;

        if (r) {
            document.getElementById('stat-daily-m').textContent = `${r.daily_m.toFixed(4)} M`;
            document.getElementById('stat-limit').innerHTML = `Limit: ${r.daily_limit_m.toFixed(2)} M | <span class="accent">${r.budget_remaining_pct.toFixed(1)}% left</span>`;

            const pctUsed = Math.min(100, (r.daily_m / r.daily_limit_m) * 100);
            const bar = document.getElementById('budget-bar');
            bar.style.width = `${pctUsed}%`;

            if (pctUsed > 90) {
                bar.style.background = 'linear-gradient(90deg, #ff4d4d, #ff1a1a)';
            }
        }
    } catch (e) {
        console.error("Failed to fetch cost", e);
    }
}

async function refreshTasks() {
    try {
        const res = await fetch('/api/tasks');
        if (!res.ok) return;
        const data = await res.json();

        const tbody = document.getElementById('tasks-table-body');
        tbody.innerHTML = '';

        if (data.tasks.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" class="text-center">No tasks available</td></tr>';
            return;
        }

        data.tasks.forEach(t => {
            const tr = document.createElement('tr');

            let statusBadge = 'bg-gray';
            if (t.state === 'running') statusBadge = 'bg-blue pulse';
            if (t.state === 'completed') statusBadge = 'bg-green';
            if (t.state === 'failed') statusBadge = 'bg-red';

            tr.innerHTML = `
                <td>${t.task_id}</td>
                <td>${t.description}</td>
                <td><span class="badge ${statusBadge}">${t.state}</span></td>
                <td>Step ${t.current_step} / ${t.max_steps}</td>
            `;
            tbody.appendChild(tr);
        });
    } catch (e) {
        console.error("Failed to fetch tasks", e);
    }
}
