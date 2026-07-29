/**
 * abgehakt — Frontend logic
 * Drag & Drop via HTML5 API, Ampel timeline indicator, Filter tabs
 */

const API = '/api/todos';
let currentFilter = 'all';
let dragSrcId = null;

// ── Init ────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    setupTheme();
    setupAddForm();
    setupTabs();
    loadTodos();
});

// ── Theme ───────────────────────────────────────────────────

function setupTheme() {
    const toggle = document.getElementById('themeToggle');
    const saved = localStorage.getItem('abgehakt-theme') || 'auto';
    applyTheme(saved === 'auto' ? (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light') : saved);
    
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
    document.getElementById('themeToggle').textContent = theme === 'dark' ? '☀️' : '🌙';
}

// ── Add Form ────────────────────────────────────────────────

function setupAddForm() {
    const form = document.getElementById('addForm');
    const expandBtn = document.getElementById('expandBtn');
    const extras = document.getElementById('addExtras');
    
    expandBtn.addEventListener('click', () => {
        const visible = extras.style.display !== 'none';
        extras.style.display = visible ? 'none' : 'flex';
        expandBtn.textContent = visible ? '📅' : '✕';
    });
    
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const title = document.getElementById('titleInput').value.trim();
        if (!title) return;
        
        const notes = document.getElementById('notesInput').value.trim();
        const dueDate = document.getElementById('dateInput').value;
        const dueTime = document.getElementById('timeInput').value;
        
        try {
            const res = await fetch(API, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ title, notes, due_date: dueDate, due_time: dueTime })
            });
            if (!res.ok) throw new Error('Failed');
            
            // Reset form
            form.reset();
            extras.style.display = 'none';
            expandBtn.textContent = '📅';
            document.getElementById('titleInput').focus();
            
            loadTodos();
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
        const res = await fetch(`${API}?filter=${currentFilter}`);
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
            deleteTodo(id);
        });
        
        // Drag & Drop
        el.setAttribute('draggable', 'true');
        
        const handle = el.querySelector('.drag-handle');
        if (handle) {
            el.addEventListener('dragstart', handleDragStart);
            el.addEventListener('dragend', handleDragEnd);
            el.addEventListener('dragover', handleDragOver);
            el.addEventListener('dragenter', handleDragEnter);
            el.addEventListener('dragleave', handleDragLeave);
            el.addEventListener('drop', handleDrop);
        }
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
    
    return `
        <div class="todo-item ${ampelClass}"
             draggable="true"
             data-id="${t.id}"
             data-order="${t.sort_order}">
            <span class="drag-handle" title="Ziehen zum Sortieren">≡</span>
            <button class="check-btn ${checkClass}" title="Abhaken">
                ${t.completed ? '✓' : ''}
            </button>
            <div class="todo-content">
                <div class="todo-title ${titleClass}">${escapeHtml(t.title)}</div>
                ${dateDisplay ? `<div class="todo-meta"><span class="todo-duedate${dateUrgent}">📅 ${dateDisplay}</span></div>` : ''}
                ${t.notes ? `<div class="todo-meta">${escapeHtml(t.notes)}</div>` : ''}
            </div>
            <button class="delete-btn" title="Löschen">✕</button>
        </div>
    `;
}

// ── Actions ─────────────────────────────────────────────────

async function toggleTodo(id) {
    try {
        await fetch(`${API}/${id}/toggle`, { method: 'PATCH' });
        loadTodos();
    } catch (err) {
        console.error('Toggle failed:', err);
    }
}

async function deleteTodo(id) {
    try {
        await fetch(`${API}/${id}`, { method: 'DELETE' });
        loadTodos();
    } catch (err) {
        console.error('Delete failed:', err);
    }
}

// ── Drag & Drop ─────────────────────────────────────────────

function handleDragStart(e) {
    dragSrcId = this.dataset.id;
    this.classList.add('dragging');
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', dragSrcId);
}

function handleDragEnd(e) {
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

function handleDragLeave(e) {
    this.classList.remove('drag-over');
}

async function handleDrop(e) {
    e.stopPropagation();
    e.preventDefault();
    this.classList.remove('drag-over');
    
    const targetId = this.dataset.id;
    if (dragSrcId === targetId) return;
    
    // Calculate new sort_order: average of surrounding items
    const items = [...document.querySelectorAll('.todo-item')];
    const targetIndex = items.indexOf(this);
    
    let prevOrder = 0;
    let nextOrder = 0;
    
    // Find previous item (not the dragged one)
    for (let i = targetIndex - 1; i >= 0; i--) {
        if (items[i].dataset.id !== dragSrcId) {
            prevOrder = parseFloat(items[i].dataset.order) || 0;
            break;
        }
    }
    
    // Find next item (not the dragged one)
    for (let i = targetIndex + 1; i < items.length; i++) {
        if (items[i].dataset.id !== dragSrcId) {
            nextOrder = parseFloat(items[i].dataset.order) || 0;
            break;
        }
    }
    
    // If no next item, use prev + 1
    if (!nextOrder && prevOrder) {
        nextOrder = prevOrder + 2;
    }
    
    const newOrder = prevOrder && nextOrder ? (prevOrder + nextOrder) / 2 : 1;
    
    try {
        const res = await fetch(`${API}/${dragSrcId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ sort_order: newOrder })
        });
        if (res.ok) {
            loadTodos();
        }
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
