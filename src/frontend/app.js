/**
 * abgehakt v2 — Frontend logic
 * V2 features: recurring todos, tags, notifications, swipe-to-delete with undo
 */

const API = '/api/todos';
const TAGS_API = '/api/tags';
let currentFilter = 'all';
let currentTagFilter = '';
let dragSrcId = null;
let allTags = [];

// ── Init ────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    setupTheme();
    setupAddForm();
    setupTabs();
    setupTagFilter();
    setupNotifications();
    loadTodos();
    loadTags();
});

// ── Theme ───────────────────────────────────────────────────

function setupTheme() {
    const toggle = document.getElementById('themeToggle');
    const saved = localStorage.getItem('abgehakt-theme') || 'auto';
    applyTheme(saved === 'auto'
        ? (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
        : saved);

    toggle.addEventListener('click', () => {
        const current = document.documentElement.getAttribute('data-theme') || 'light';
        const next = current === 'dark' ? 'light' : 'dark';
        applyTheme(next);
        localStorage.setItem('abgehakt-theme', next);
    });

    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', e => {
        if (localStorage.getItem('abgehakt-theme') === 'auto') {
            applyTheme(e.matches ? 'dark' : 'light');
        }
    });
}

function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    document.getElementById('themeToggle').textContent = theme === 'dark' ? '\u2600\uFE0F' : '\uD83C\uDF19';
}

// ── Notifications ───────────────────────────────────────────

function setupNotifications() {
    const notifyBtn = document.getElementById('notifyBtn');

    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.register('/sw.js').catch(() => {
            // Offline support is optional; the app remains usable without it.
        });
    }

    if (!('Notification' in window)) {
        notifyBtn.disabled = true;
        notifyBtn.title = 'Benachrichtigungen werden nicht unterstützt';
    } else {
        updateNotificationButton();
        notifyBtn.addEventListener('click', requestNotificationPermission);
    }

    // Client-side reminders work while the tab/PWA is running.
    setInterval(checkDueNotifications, 60000);
    setTimeout(checkDueNotifications, 2000);
}

async function checkDueNotifications() {
    if (!('Notification' in window)) return;
    if (Notification.permission !== 'granted') return;

    try {
        const res = await fetch(`${API}?filter=today`);
        const todos = await res.json();
        const now = new Date();
        const nowTime = String(now.getHours()).padStart(2, '0') + ':' +
                        String(now.getMinutes()).padStart(2, '0');

        // Send notifications for todos due now
        for (const t of todos) {
            if (t.completed) continue;
            if (!t.due_time) continue;

            // Notify if time matches (within the minute)
            const todoTime = t.due_time.substring(0, 5);
            if (todoTime === nowTime) {
                const notifiedKey = 'notified-' + t.id + '-' + todoTime;
                if (localStorage.getItem(notifiedKey) === 'sent') continue;

                await showDueNotification(t);
                localStorage.setItem(notifiedKey, 'sent');
            }
        }
    } catch (e) {
        // Silently ignore – notifications are best-effort
    }
}

async function showDueNotification(todo) {
    const options = {
        body: todo.title,
        icon: '/icon-192.png',
        badge: '/icon-192.png',
        tag: todo.id,
        data: { url: '/' },
        vibrate: [200, 100, 200],
    };

    // Service-worker notifications also work in installed iOS PWAs.
    if ('serviceWorker' in navigator) {
        const registration = await navigator.serviceWorker.ready;
        await registration.showNotification('\u23F0 abgehakt: F\u00e4llig!', options);
        return;
    }

    const notification = new Notification('\u23F0 abgehakt: F\u00e4llig!', options);
    notification.onclick = () => {
        window.focus();
        notification.close();
    };
}

function updateNotificationButton() {
    const notifyBtn = document.getElementById('notifyBtn');
    if (!notifyBtn || !('Notification' in window)) return;
    const permission = Notification.permission;
    notifyBtn.classList.toggle('active', permission === 'granted');
    notifyBtn.textContent = permission === 'granted' ? '\uD83D\uDD14' : '\uD83D\uDD15';
    notifyBtn.title = permission === 'granted'
        ? 'Benachrichtigungen sind aktiviert'
        : permission === 'denied'
            ? 'Benachrichtigungen wurden im Browser blockiert'
            : 'Benachrichtigungen aktivieren';
}

async function requestNotificationPermission() {
    if (!('Notification' in window)) return;
    if (Notification.permission === 'denied') {
        showToast('\uD83D\uDD15 Bitte Benachrichtigungen in den Browser-Einstellungen erlauben.');
        return;
    }
    if (Notification.permission === 'default') {
        const permission = await Notification.requestPermission();
        updateNotificationButton();
        if (permission === 'granted') {
            showToast('\uD83D\uDD14 Benachrichtigungen aktiviert!');
            checkDueNotifications();
        }
        return;
    }
    showToast('\uD83D\uDD14 Benachrichtigungen sind bereits aktiviert.');
}

// ── Tag Filter ──────────────────────────────────────────────

function setupTagFilter() {
    const container = document.getElementById('tagFilterChips');
    if (!container) return;

    container.addEventListener('click', (e) => {
        const chip = e.target.closest('.tag-chip');
        if (!chip) return;

        const tag = chip.dataset.tag;
        if (currentTagFilter === tag) {
            currentTagFilter = '';
        } else {
            currentTagFilter = tag;
        }
        updateTagChipUI();
        loadTodos();
    });
}

async function loadTags() {
    try {
        const res = await fetch(TAGS_API);
        allTags = await res.json();
    } catch (e) {
        allTags = [];
    }
    renderTagChips();
}

function renderTagChips() {
    const container = document.getElementById('tagFilterChips');
    if (!container) return;
    if (!allTags.length) {
        container.innerHTML = '';
        return;
    }
    container.innerHTML = allTags.map(tag =>
        `<span class="tag-chip" data-tag="${escapeHtml(tag)}">#${escapeHtml(tag)}</span>`
    ).join('');
    updateTagChipUI();
}

function updateTagChipUI() {
    document.querySelectorAll('.tag-chip').forEach(chip => {
        chip.classList.toggle('active', chip.dataset.tag === currentTagFilter);
    });
}

// ── Add Form ────────────────────────────────────────────────

function setupAddForm() {
    const form = document.getElementById('addForm');
    const expandBtn = document.getElementById('expandBtn');
    const extras = document.getElementById('addExtras');

    expandBtn.addEventListener('click', () => {
        const visible = extras.style.display !== 'none';
        extras.style.display = visible ? 'none' : 'flex';
        expandBtn.textContent = visible ? '\uD83D\uDCC5' : '\u2715';
    });

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const title = document.getElementById('titleInput').value.trim();
        if (!title) return;

        const notes = document.getElementById('notesInput').value.trim();
        const dueDate = document.getElementById('dateInput').value;
        const dueTime = document.getElementById('timeInput').value;
        const recurring = document.getElementById('recurringSelect').value;
        const tags = document.getElementById('tagsInput').value.trim();

        // Build notify_at
        const notifyAt = document.getElementById('notifyCheck')?.checked ? 'due' : '';

        try {
            const res = await fetch(API, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    title, notes,
                    due_date: dueDate, due_time: dueTime,
                    recurring, tags, notify_at: notifyAt,
                }),
            });
            if (!res.ok) throw new Error('Failed');

            // Reset form
            form.reset();
            extras.style.display = 'none';
            expandBtn.textContent = '\uD83D\uDCC5';
            document.getElementById('titleInput').focus();
            document.getElementById('recurringSelect').value = '';

            loadTodos();
            loadTags();
        } catch (err) {
            console.error('Add todo failed:', err);
        }
    });
}

// ── Filter Tabs ─────────────────────────────────────────────

function setupTabs() {
    document.querySelectorAll('.tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            currentFilter = tab.dataset.filter;
            loadTodos();
        });
    });
}

// ── Load & Render ───────────────────────────────────────────

async function loadTodos() {
    try {
        let url = `${API}?filter=${currentFilter}`;
        if (currentTagFilter) url += `&tag=${encodeURIComponent(currentTagFilter)}`;
        const res = await fetch(url);
        if (!res.ok) throw new Error('Failed');
        const todos = await res.json();
        renderTodos(todos);
    } catch (err) {
        console.error('Load todos failed:', err);
    }
}

function renderTodos(todos) {
    const list = document.getElementById('todoList');
    const empty = document.getElementById('emptyState');

    if (!todos.length) {
        list.innerHTML = '';
        empty.style.display = 'block';
        return;
    }

    empty.style.display = 'none';
    list.innerHTML = todos.map(t => createTodoHTML(t)).join('');

    // Attach event listeners
    list.querySelectorAll('.todo-item').forEach(el => {
        const id = el.dataset.id;

        // Checkbox
        el.querySelector('.check-btn').addEventListener('click', () => toggleTodo(id));

        // Delete
        el.querySelector('.delete-btn').addEventListener('click', (e) => {
            e.stopPropagation();
            deleteTodoWithUndo(id, el);
        });

        // Swipe to delete
        setupSwipe(el, id);

        // Inline tag click
        el.querySelectorAll('.todo-tag').forEach(tagEl => {
            tagEl.addEventListener('click', (e) => {
                e.stopPropagation();
                currentTagFilter = tagEl.dataset.tag;
                updateTagChipUI();
                loadTodos();
            });
        });

        // Drag & Drop
        el.setAttribute('draggable', 'true');
        el.addEventListener('dragstart', handleDragStart);
        el.addEventListener('dragend', handleDragEnd);
        el.addEventListener('dragover', handleDragOver);
        el.addEventListener('dragenter', handleDragEnter);
        el.addEventListener('dragleave', handleDragLeave);
        el.addEventListener('drop', handleDrop);
    });
}

function createTodoHTML(t) {
    const isToday = t.due_date === getTodayISO();
    const isOverdue = t.due_date && t.due_date < getTodayISO();
    const isPastTime = isToday && t.due_time && t.due_time < getNowTime();

    let ampelClass = '';
    if (t.completed) {
        ampelClass = 'completed';
    } else if (isOverdue || isPastTime) {
        ampelClass = 'overdue';
    } else if (isToday) {
        ampelClass = 'today';
    } else if (t.due_date) {
        ampelClass = 'future';
    }

    const dateDisplay = t.due_date ? formatDate(t.due_date, t.due_time) : '';
    const dateUrgent = (!t.completed && (isOverdue || isPastTime)) ? ' urgent' : '';
    const titleClass = t.completed ? 'strikethrough' : '';
    const checkClass = t.completed ? 'checked' : '';

    // Recurring badge
    const recurringLabels = { daily: '\uD83D\uDD04 t\u00e4glich', weekly: '\uD83D\uDD04 w\u00f6chentlich', monthly: '\uD83D\uDD04 monatlich', yearly: '\uD83D\uDD04 j\u00e4hrlich' };
    const recurringBadge = t.recurring ? `<span class="recurring-badge">${recurringLabels[t.recurring] || '\uD83D\uDD04 ' + t.recurring}</span>` : '';

    // Tags
    const tagList = (t.tags || '') ? t.tags.split(',').map(s => s.trim()).filter(Boolean) : [];
    const tagsHtml = tagList.map(tag =>
        `<span class="todo-tag" data-tag="${escapeHtml(tag)}">#${escapeHtml(tag)}</span>`
    ).join(' ');

    // Notify indicator
    const notifyIcon = t.notify_at === 'due' ? ' \uD83D\uDD14' : '';

    return `
        <div class="todo-item ${ampelClass}"
             draggable="true"
             data-id="${t.id}"
             data-order="${t.sort_order}">
            <span class="drag-handle" title="Ziehen zum Sortieren">\u2261</span>
            <button class="check-btn ${checkClass}" title="Abhaken">
                ${t.completed ? '\u2713' : ''}
            </button>
            <div class="todo-content">
                <div class="todo-title ${titleClass}">${escapeHtml(t.title)}${notifyIcon}</div>
                <div class="todo-meta-row">
                    ${dateDisplay ? `<span class="todo-duedate${dateUrgent}">\uD83D\uDCC5 ${dateDisplay}</span>` : ''}
                    ${recurringBadge}
                </div>
                ${tagsHtml ? `<div class="todo-tags-row">${tagsHtml}</div>` : ''}
                ${t.notes ? `<div class="todo-meta notes-text">${escapeHtml(t.notes)}</div>` : ''}
            </div>
            <button class="delete-btn" title="L\u00f6schen">\u2715</button>
        </div>
    `;
}

// ── Swipe to Delete ─────────────────────────────────────────

function setupSwipe(el, id) {
    let startX = 0;
    let currentX = 0;
    let swiping = false;

    el.addEventListener('touchstart', (e) => {
        if (e.target.closest('.delete-btn, .check-btn, .todo-tag, .drag-handle')) return;
        startX = e.touches[0].clientX;
        currentX = startX;
        swiping = true;
        el.style.transition = 'none';
    }, { passive: true });

    el.addEventListener('touchmove', (e) => {
        if (!swiping) return;
        currentX = e.touches[0].clientX;
        const diff = currentX - startX;
        // Only allow left swipe
        if (diff > 10) { swiping = false; el.style.transform = ''; return; }
        if (diff < -10) {
            el.style.transform = `translateX(${diff}px)`;
            el.style.opacity = Math.max(0.3, 1 + diff / 200);
        }
    }, { passive: true });

    el.addEventListener('touchend', () => {
        if (!swiping) { el.style.transform = ''; el.style.opacity = ''; return; }
        swiping = false;
        const diff = currentX - startX;
        el.style.transition = 'transform 0.2s, opacity 0.2s';

        if (diff < -80) {
            // Delete!
            el.style.transform = 'translateX(-120%)';
            el.style.opacity = '0';
            setTimeout(() => deleteTodoWithUndo(id, el), 200);
        } else {
            el.style.transform = '';
            el.style.opacity = '';
        }
    });
}

// ── Actions ─────────────────────────────────────────────────

async function toggleTodo(id) {
    try {
        const res = await fetch(`${API}/${id}/toggle`, { method: 'PATCH' });
        if (!res.ok) throw new Error('Toggle failed');
        const data = await res.json();

        // If a new recurring instance was created, show a quick toast
        if (data.next) {
            showToast('\uD83D\uDD04 N\u00e4chste Instanz: ' + data.next.due_date);
        }

        loadTodos();
    } catch (err) {
        console.error('Toggle failed:', err);
    }
}

async function deleteTodoWithUndo(id, el) {
    try {
        const res = await fetch(`${API}/${id}`, { method: 'DELETE' });
        if (!res.ok) throw new Error('Delete failed');

        // Show undo notification
        showUndoNotification(id, el);
    } catch (err) {
        console.error('Delete failed:', err);
        if (el) { el.style.transform = ''; el.style.opacity = ''; }
    }
}

function showUndoNotification(id, el) {
    // Remove existing undo bar
    const existing = document.querySelector('.undo-bar');
    if (existing) existing.remove();

    const bar = document.createElement('div');
    bar.className = 'undo-bar';
    bar.innerHTML = `
        <span>🗑️ Gelöscht</span>
        <button class="undo-btn">Rückgängig</button>
        <button class="undo-dismiss">✕</button>
    `;
    bar.querySelector('.undo-btn').addEventListener('click', async () => {
        try {
            await fetch(`${API}/${id}/undo`, { method: 'POST' });
            bar.remove();
            loadTodos();
        } catch (e) {
            console.error('Undo failed:', e);
        }
    });
    bar.querySelector('.undo-dismiss').addEventListener('click', () => {
        bar.remove();
        loadTodos();
    });

    const list = document.getElementById('todoList');
    list.parentNode.insertBefore(bar, list.nextSibling);

    // Auto-dismiss after 6 seconds
    setTimeout(() => {
        if (bar.parentNode) {
            bar.remove();
            loadTodos();
        }
    }, 6000);
}

function showToast(msg) {
    const existing = document.querySelector('.toast');
    if (existing) existing.remove();

    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.textContent = msg;
    document.body.appendChild(toast);

    setTimeout(() => toast.classList.add('show'), 10);
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// ── Drag & Drop ─────────────────────────────────────────────

function handleDragStart(e) {
    dragSrcId = this.dataset.id;
    this.classList.add('dragging');
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', dragSrcId);
}

function handleDragEnd() {
    this.classList.remove('dragging');
    document.querySelectorAll('.drag-over').forEach(el => el.classList.remove('drag-over'));
    dragSrcId = null;
}

function handleDragOver(e) {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    return false;
}

function handleDragEnter(e) {
    e.preventDefault();
    if (this.dataset.id !== dragSrcId) {
        this.classList.add('drag-over');
    }
}

function handleDragLeave() {
    this.classList.remove('drag-over');
}

async function handleDrop(e) {
    e.stopPropagation();
    e.preventDefault();
    this.classList.remove('drag-over');

    const targetId = this.dataset.id;
    if (dragSrcId === targetId) return;

    const items = [...document.querySelectorAll('.todo-item')];
    const targetIndex = items.indexOf(this);

    let prevOrder = 0;
    let nextOrder = 0;

    for (let i = targetIndex - 1; i >= 0; i--) {
        if (items[i].dataset.id !== dragSrcId) {
            prevOrder = parseFloat(items[i].dataset.order) || 0;
            break;
        }
    }
    for (let i = targetIndex + 1; i < items.length; i++) {
        if (items[i].dataset.id !== dragSrcId) {
            nextOrder = parseFloat(items[i].dataset.order) || 0;
            break;
        }
    }
    if (!nextOrder && prevOrder) nextOrder = prevOrder + 2;

    const newOrder = prevOrder && nextOrder ? (prevOrder + nextOrder) / 2 : 1;

    try {
        const res = await fetch(`${API}/${dragSrcId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ sort_order: newOrder }),
        });
        if (res.ok) loadTodos();
    } catch (err) {
        console.error('Drag update failed:', err);
    }
}

// ── Helpers ─────────────────────────────────────────────────

function getTodayISO() {
    const d = new Date();
    return d.getFullYear() + '-' +
        String(d.getMonth() + 1).padStart(2, '0') + '-' +
        String(d.getDate()).padStart(2, '0');
}

function getNowTime() {
    const d = new Date();
    return String(d.getHours()).padStart(2, '0') + ':' +
           String(d.getMinutes()).padStart(2, '0');
}

function formatDate(dateStr, timeStr) {
    if (!dateStr) return '';
    const [y, m, d] = dateStr.split('-');
    const display = `${d}.${m}.`;
    return timeStr ? `${display} ${timeStr}` : display;
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}
