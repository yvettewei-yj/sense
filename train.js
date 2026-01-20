/**
 * PM用户Sense训练系统 - 训练页面交互逻辑
 */

// 全局状态
let currentSession = null;
let currentProfile = null;
let isLoading = false;
let selectedScenarioId = 'random';
let selectedMentalStateId = 'random';
let profilesCache = [];
let recommendedProfileId = null;
let lastDrawerProfileId = null;
let startAbortController = null;
let startElapsedTimer = null;
let startElapsedSec = 0;

// DOM 元素
const elements = {
    stages: {
        select: document.getElementById('select-stage'),
        chat: document.getElementById('chat-stage'),
        result: document.getElementById('result-stage')
    },
    profilesList: document.getElementById('profiles-list'),
    chatMessages: document.getElementById('chat-messages'),
    messageInput: document.getElementById('message-input'),
    sendBtn: document.getElementById('send-btn'),
    endChatBtn: document.getElementById('end-chat-btn'),
    quickStartBtn: document.getElementById('quick-start-btn'),
    drawer: document.getElementById('profile-drawer'),
    drawerOverlay: document.getElementById('profile-drawer-overlay'),
    drawerCloseBtn: document.getElementById('drawer-close-btn'),
    drawerCancelBtn: document.getElementById('drawer-cancel-btn'),
    drawerStartBtn: document.getElementById('drawer-start-btn'),
    startOverlay: document.getElementById('start-overlay'),
    startElapsed: document.getElementById('start-elapsed'),
    startCancelBtn: document.getElementById('start-cancel-btn')
};

// ===== Radar Chart (Canvas) =====
let lastRadarData = null;
let radarResizeTimer = null;
let evaluationCriteriaCache = null;

function clamp(n, min, max) {
    return Math.max(min, Math.min(max, n));
}

function isFiniteNumber(x) {
    return typeof x === 'number' && Number.isFinite(x);
}

function drawRadarChart(canvas, labels, values) {
    if (!canvas) return;
    const parent = canvas.parentElement;
    const cssW = Math.max(320, Math.min(560, parent ? parent.clientWidth : 560));
    const cssH = 360;
    const dpr = window.devicePixelRatio || 1;
    canvas.style.width = `${cssW}px`;
    canvas.style.height = `${cssH}px`;
    canvas.width = Math.floor(cssW * dpr);
    canvas.height = Math.floor(cssH * dpr);

    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, cssW, cssH);

    // 给标签更大边距，避免被裁切
    const padding = 58;
    const cx = cssW / 2;
    const cy = cssH / 2 + 6;
    const R = Math.min(cssW, cssH) / 2 - padding;
    const n = labels.length;
    if (!n) return;

    // Colors (match theme)
    const grid = 'rgba(15, 23, 42, 0.10)';
    const axis = 'rgba(15, 23, 42, 0.15)';
    const fill = 'rgba(22, 119, 255, 0.18)';
    const stroke = 'rgba(22, 119, 255, 0.85)';
    const dot = 'rgba(22, 119, 255, 1)';
    const text = 'rgba(15, 23, 42, 0.75)';

    // Grid rings
    ctx.lineWidth = 1;
    for (let k = 1; k <= 5; k++) {
        const r = (R * k) / 5;
        ctx.beginPath();
        for (let i = 0; i < n; i++) {
            const ang = -Math.PI / 2 + (2 * Math.PI * i) / n;
            const x = cx + r * Math.cos(ang);
            const y = cy + r * Math.sin(ang);
            if (i === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        }
        ctx.closePath();
        ctx.strokeStyle = grid;
        ctx.stroke();
    }

    // Axes + labels
    ctx.font = '12px "Noto Sans SC", system-ui, -apple-system, sans-serif';
    ctx.fillStyle = text;
    for (let i = 0; i < n; i++) {
        const ang = -Math.PI / 2 + (2 * Math.PI * i) / n;
        const x2 = cx + R * Math.cos(ang);
        const y2 = cy + R * Math.sin(ang);
        ctx.beginPath();
        ctx.moveTo(cx, cy);
        ctx.lineTo(x2, y2);
        ctx.strokeStyle = axis;
        ctx.stroke();

        const lx = cx + (R + 18) * Math.cos(ang);
        const ly = cy + (R + 18) * Math.sin(ang);
        const label = labels[i] || '';
        const m = ctx.measureText(label);
        const alignRight = Math.cos(ang) < -0.35;
        const alignLeft = Math.cos(ang) > 0.35;
        let tx = lx;
        if (alignRight) tx = lx - m.width;
        else if (!alignLeft) tx = lx - m.width / 2;
        const ty = ly + (Math.sin(ang) > 0.2 ? 12 : 0);
        // clamp 到画布内，避免“显示不完全”
        const tx2 = clamp(tx, 8, cssW - m.width - 8);
        const ty2 = clamp(ty, 14, cssH - 8);
        ctx.fillText(label, tx2, ty2);
    }

    // Data polygon
    const pts = values.map((v, i) => {
        const vv = clamp(Number(v) || 0, 0, 100) / 100;
        const ang = -Math.PI / 2 + (2 * Math.PI * i) / n;
        return {
            x: cx + (R * vv) * Math.cos(ang),
            y: cy + (R * vv) * Math.sin(ang),
        };
    });

    ctx.beginPath();
    pts.forEach((p, i) => (i === 0 ? ctx.moveTo(p.x, p.y) : ctx.lineTo(p.x, p.y)));
    ctx.closePath();
    ctx.fillStyle = fill;
    ctx.fill();
    ctx.strokeStyle = stroke;
    ctx.lineWidth = 2;
    ctx.stroke();

    // Dots
    ctx.fillStyle = dot;
    pts.forEach(p => {
        ctx.beginPath();
        ctx.arc(p.x, p.y, 3.2, 0, Math.PI * 2);
        ctx.fill();
    });
}

function renderRadarFromScores(scores) {
    const canvas = document.getElementById('radar-canvas');
    const wrap = canvas ? canvas.closest('.radar-wrap') : null;
    const empty = document.getElementById('radar-empty');
    if (!canvas || !scores) {
        if (wrap) wrap.classList.add('is-empty');
        if (empty) empty.setAttribute('aria-hidden', 'false');
        return;
    }
    const labels = ['沟通技巧', '同理心', '问题解决', '说服力', '专业度'];
    const raw = [
        scores.communication_skills,
        scores.empathy,
        scores.problem_solving,
        scores.persuasion,
        scores.professionalism,
    ];
    const parsed = raw.map(v => {
        const n = Number(v);
        return Number.isFinite(n) ? clamp(n, 0, 100) : null;
    });

    const complete = parsed.every(v => v !== null);
    if (!complete) {
        if (wrap) wrap.classList.add('is-empty');
        if (empty) empty.setAttribute('aria-hidden', 'false');
        lastRadarData = null;
        // 仍然画一个空网格，避免留白
        drawRadarChart(canvas, labels, parsed.map(v => (v === null ? 0 : v)));
        return;
    }

    if (wrap) wrap.classList.remove('is-empty');
    if (empty) empty.setAttribute('aria-hidden', 'true');
    lastRadarData = { labels, values: parsed };
    drawRadarChart(canvas, labels, parsed);
}

async function loadEvaluationCriteriaOnce() {
    if (evaluationCriteriaCache) return evaluationCriteriaCache;
    try {
        const resp = await fetch('/api/evaluation-criteria');
        const data = await safeReadJson(resp);
        if (data && typeof data === 'object') {
            evaluationCriteriaCache = data;
        } else {
            evaluationCriteriaCache = {};
        }
    } catch (e) {
        evaluationCriteriaCache = {};
    }
    return evaluationCriteriaCache;
}

async function safeReadJson(response) {
    try {
        const contentType = response.headers.get('content-type') || '';
        if (contentType.includes('application/json')) {
            return await response.json();
        }
        const text = await response.text();
        // 有些环境可能返回 HTML 错误页，这里尽量给出可读信息
        return { error: text.slice(0, 300) || '非JSON响应' };
    } catch (e) {
        return { error: `解析响应失败: ${e.message || e}` };
    }
}

async function loadTrainingOptions() {
    try {
        const response = await fetch('/api/training/options');
        const data = await safeReadJson(response);
        const scenarios = data.scenarios || [];
        const mentalStates = data.mental_states || [];

        const scenarioSelect = document.getElementById('scenario-select');
        const mentalSelect = document.getElementById('mental-select');
        if (!scenarioSelect || !mentalSelect) return;

        // 保留 random
        scenarioSelect.innerHTML = `<option value="random">随机</option>` + scenarios.map(s => (
            `<option value="${s.id}">${s.name}</option>`
        )).join('');
        mentalSelect.innerHTML = `<option value="random">随机</option>` + mentalStates.map(m => (
            `<option value="${m.id}">${m.name}</option>`
        )).join('');

        scenarioSelect.addEventListener('change', () => {
            selectedScenarioId = scenarioSelect.value;
        });
        mentalSelect.addEventListener('change', () => {
            selectedMentalStateId = mentalSelect.value;
        });
    } catch (e) {
        console.error('加载训练配置失败:', e);
    }
}

// 工具函数
function getAvatarEmoji(occupation) {
    const map = {
        '退休教师': '👩‍🏫',
        '互联网程序员': '👨‍💻',
        '全职妈妈': '👩‍👧',
        '个体户老板': '👨‍💼',
        '大四学生': '👨‍🎓'
    };
    return map[occupation] || '👤';
}

function getDifficultyClass(stars) {
    if (stars <= 1) return 'easy';
    if (stars <= 2) return 'medium';
    return 'hard';
}

function computeRecommendedProfileId(profiles) {
    if (!Array.isArray(profiles) || profiles.length === 0) return null;
    const sorted = [...profiles].sort((a, b) => {
        const as = Number(a.difficulty_stars || 3);
        const bs = Number(b.difficulty_stars || 3);
        if (as !== bs) return as - bs;
        const at = Number(a.trust_threshold || 10);
        const bt = Number(b.trust_threshold || 10);
        if (at !== bt) return at - bt;
        return Number(a.id || 0) - Number(b.id || 0);
    });
    return sorted[0]?.id ?? null;
}

function setButtonLoading(btn, loadingText = '加载中...') {
    if (!btn) return () => {};
    const prev = {
        text: btn.textContent,
        disabled: btn.disabled
    };
    btn.textContent = loadingText;
    btn.disabled = true;
    return () => {
        btn.textContent = prev.text;
        btn.disabled = prev.disabled;
    };
}

function showStartOverlay() {
    if (!elements.startOverlay) return;
    startElapsedSec = 0;
    if (elements.startElapsed) elements.startElapsed.textContent = '0';
    elements.startOverlay.classList.add('show');
    elements.startOverlay.setAttribute('aria-hidden', 'false');
    if (startElapsedTimer) clearInterval(startElapsedTimer);
    startElapsedTimer = setInterval(() => {
        startElapsedSec += 1;
        if (elements.startElapsed) elements.startElapsed.textContent = String(startElapsedSec);
    }, 1000);
}

function hideStartOverlay() {
    if (!elements.startOverlay) return;
    elements.startOverlay.classList.remove('show');
    elements.startOverlay.setAttribute('aria-hidden', 'true');
    if (startElapsedTimer) {
        clearInterval(startElapsedTimer);
        startElapsedTimer = null;
    }
}

// 切换阶段
function switchStage(stageName) {
    Object.values(elements.stages).forEach(stage => {
        stage.classList.remove('active');
    });
    elements.stages[stageName].classList.add('active');
}

function findProfileById(profileId) {
    return profilesCache.find(p => Number(p.id) === Number(profileId)) || null;
}

function renderProfiles(profiles) {
    recommendedProfileId = computeRecommendedProfileId(profiles);

    const sorted = [...profiles].sort((a, b) => {
        const aRec = Number(a.id) === Number(recommendedProfileId) ? 0 : 1;
        const bRec = Number(b.id) === Number(recommendedProfileId) ? 0 : 1;
        if (aRec !== bRec) return aRec - bRec;
        return Number(a.id || 0) - Number(b.id || 0);
    });

    elements.profilesList.innerHTML = sorted.map(profile => {
        const isRec = Number(profile.id) === Number(recommendedProfileId);
        const badge = isRec ? `<span class="profile-select-badge recommend">推荐</span>` : '';
        return `
            <div class="profile-select-card ${isRec ? 'recommended' : ''}" data-id="${profile.id}" tabindex="0" role="button" aria-label="查看${profile.name}档案">
                <div class="profile-select-avatar" aria-hidden="true">${getAvatarEmoji(profile.occupation)}</div>
                <div class="profile-select-info">
                    <div class="profile-select-header">
                        <span class="profile-select-name">${profile.name}</span>
                        ${badge}
                        <span class="profile-select-meta">${profile.age}岁 · ${profile.occupation}</span>
                        <span class="profile-select-difficulty ${getDifficultyClass(profile.difficulty_stars)}">
                            ${'⭐'.repeat(profile.difficulty_stars)} ${profile.difficulty}
                        </span>
                    </div>
                    <div class="profile-select-scenario">${profile.trigger_scenario}</div>
                </div>
                <div class="profile-select-action">
                    <button class="start-btn" data-action="start" data-id="${profile.id}" type="button">开始训练</button>
                    <button class="profile-link-btn" data-action="preview" data-id="${profile.id}" type="button">查看档案</button>
                </div>
            </div>
        `;
    }).join('');
}

// 加载用户画像列表
async function loadProfiles() {
    try {
        const response = await fetch('/api/profiles');
        const data = await safeReadJson(response);
        const profiles = Array.isArray(data) ? data : [];
        profilesCache = profiles;

        renderProfiles(profilesCache);

        // 启用一键开局
        if (elements.quickStartBtn) {
            elements.quickStartBtn.disabled = profilesCache.length === 0;
        }
    } catch (error) {
        console.error('加载用户画像失败:', error);
        elements.profilesList.innerHTML = '<p style="text-align:center;color:var(--danger)">加载失败，请刷新页面重试</p>';
        if (elements.quickStartBtn) elements.quickStartBtn.disabled = true;
    }
}

// 开始训练
async function startTraining(profileId, triggerBtn = null) {
    const restoreBtn = setButtonLoading(triggerBtn, '加载中...');
    try {
        // 显示加载状态（不依赖全局 event）
        if (startAbortController) {
            try { startAbortController.abort(); } catch (_) {}
        }
        startAbortController = new AbortController();
        showStartOverlay();

        const response = await fetch('/api/session/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                profile_id: profileId,
                scenario_id: selectedScenarioId,
                mental_state_id: selectedMentalStateId
            }),
            signal: startAbortController.signal
        });
        
        const data = await safeReadJson(response);
        
        if (response.ok) {
            currentSession = data.session_id;
            currentProfile = data.profile;
            
            // 初始化对话界面
            initChatUI(data);
            
            // 添加开场消息
            addMessage('user', data.opening_message, data.inner_thought);
            
            // 切换到对话阶段
            switchStage('chat');
        } else {
            alert(data.error || '启动训练失败');
        }
    } catch (error) {
        if (error?.name === 'AbortError') {
            return;
        }
        console.error('启动训练失败:', error);
        alert('启动训练失败，请重试');
    } finally {
        // 成功时页面会切换阶段，但按钮可能仍存在于 DOM（如 Drawer），这里统一复原，避免“加载中”卡死
        hideStartOverlay();
        startAbortController = null;
        restoreBtn();
    }
}

function getSelectedOptionText(selectId) {
    const el = document.getElementById(selectId);
    if (!el) return '';
    const opt = el.options?.[el.selectedIndex];
    return (opt?.textContent || '').trim();
}

function syncDrawerSelectedOptions() {
    const scenarioEl = document.getElementById('drawer-sel-scenario');
    const mentalEl = document.getElementById('drawer-sel-mental');
    const scenarioText = getSelectedOptionText('scenario-select') || '随机';
    const mentalText = getSelectedOptionText('mental-select') || '随机';
    if (scenarioEl) scenarioEl.textContent = `场景：${scenarioText}`;
    if (mentalEl) mentalEl.textContent = `心理：${mentalText}`;
}

function openProfileDrawer(profileId) {
    const profile = findProfileById(profileId);
    if (!profile) return;

    lastDrawerProfileId = profile.id;

    // 填充内容
    const avatar = document.getElementById('drawer-avatar');
    const name = document.getElementById('drawer-name');
    const meta = document.getElementById('drawer-meta');
    const diff = document.getElementById('drawer-difficulty');
    const trigger = document.getElementById('drawer-trigger');
    const background = document.getElementById('drawer-background');
    const goal = document.getElementById('drawer-goal');
    const risk = document.getElementById('drawer-risk');
    const personality = document.getElementById('drawer-personality');
    const pains = document.getElementById('drawer-pains');

    if (avatar) avatar.textContent = getAvatarEmoji(profile.occupation);
    if (name) name.textContent = profile.name;
    if (meta) meta.textContent = `${profile.age}岁 · ${profile.occupation} · 信任阈值 ${profile.trust_threshold}/10`;
    if (diff) diff.textContent = `${'⭐'.repeat(profile.difficulty_stars)} ${profile.difficulty}`;
    if (trigger) trigger.textContent = profile.trigger_scenario || '-';
    if (background) background.textContent = profile.background || '-';
    if (goal) goal.textContent = profile.investment_goal || '-';
    if (risk) risk.textContent = profile.risk_tolerance || '-';
    if (personality) personality.textContent = profile.personality || '-';
    if (pains) {
        const list = Array.isArray(profile.pain_points) ? profile.pain_points : [];
        pains.innerHTML = list.map(p => `<li>${p}</li>`).join('');
    }

    syncDrawerSelectedOptions();

    document.body.classList.add('drawer-open');
    if (elements.drawerOverlay) elements.drawerOverlay.setAttribute('aria-hidden', 'false');
    if (elements.drawer) elements.drawer.setAttribute('aria-hidden', 'false');

    // 焦点给关闭按钮
    if (elements.drawerCloseBtn) elements.drawerCloseBtn.focus();
}

function closeProfileDrawer() {
    document.body.classList.remove('drawer-open');
    if (elements.drawerOverlay) elements.drawerOverlay.setAttribute('aria-hidden', 'true');
    if (elements.drawer) elements.drawer.setAttribute('aria-hidden', 'true');
}

// 初始化对话界面
function initChatUI(data) {
    const profile = data.profile;
    const scenario = data.scenario;
    const mentalState = data.mental_state;
    
    // 设置用户信息
    document.getElementById('chat-user-avatar').textContent = getAvatarEmoji(profile.occupation);
    document.getElementById('chat-user-name').textContent = profile.name;
    document.getElementById('chat-user-meta').textContent = `${profile.age}岁 · ${profile.occupation}`;
    document.getElementById('chat-user-background').textContent = profile.background;

    const scenarioEl = document.getElementById('chat-scenario');
    const mentalEl = document.getElementById('chat-mental');
    if (scenarioEl) scenarioEl.textContent = `场景：${scenario?.name || '-'}`;
    if (mentalEl) mentalEl.textContent = `心理：${mentalState?.name || '-'}`;
    
    // 设置顾虑列表
    const concernsList = document.getElementById('concerns-list');
    concernsList.innerHTML = profile.pain_points.map(p => `<li>${p}</li>`).join('');
    
    // 重置状态
    updateStatus(data.status);
    
    // 清空消息
    elements.chatMessages.innerHTML = '';
    elements.messageInput.value = '';
}

// 更新状态显示
function updateStatus(status) {
    document.getElementById('turn-count').textContent = status.turn_count;
    document.getElementById('trust-text').textContent = `${status.trust_level}/${status.trust_threshold}`;
    document.getElementById('concerns-count').textContent = `${status.concerns_addressed.length}/${status.total_concerns}`;
    
    // 更新信任度进度条
    const progress = (status.trust_level / 10) * 100;
    document.getElementById('trust-progress').style.width = `${progress}%`;
    
    // 更新顾虑列表状态
    const concernItems = document.querySelectorAll('#concerns-list li');
    concernItems.forEach((item, index) => {
        const concern = currentProfile.pain_points[index];
        if (status.concerns_addressed.includes(concern)) {
            item.classList.add('addressed');
        }
    });
}

// 添加消息到对话区
function addMessage(role, content, innerThought = '', trustChange = 0) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `chat-message ${role}`;
    
    const avatar = role === 'user' ? getAvatarEmoji(currentProfile.occupation) : '💼';
    
    let metaHtml = '';
    if (role === 'user') {
        if (innerThought) {
            metaHtml += `<span class="inner-thought">💭 ${innerThought}</span>`;
        }
        if (trustChange !== 0) {
            const changeClass = trustChange > 0 ? 'positive' : 'negative';
            const changeText = trustChange > 0 ? `+${trustChange}` : trustChange;
            metaHtml += `<span class="trust-change ${changeClass}">信任度 ${changeText}</span>`;
        }
    }
    
    messageDiv.innerHTML = `
        <div class="chat-avatar">${avatar}</div>
        <div class="chat-content">
            <div class="chat-bubble">${content}</div>
            ${metaHtml ? `<div class="chat-meta">${metaHtml}</div>` : ''}
        </div>
    `;
    
    elements.chatMessages.appendChild(messageDiv);
    elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight;
}

// 添加加载指示器
function addTypingIndicator() {
    const indicator = document.createElement('div');
    indicator.className = 'chat-message user';
    indicator.id = 'typing-indicator';
    indicator.innerHTML = `
        <div class="chat-avatar">${getAvatarEmoji(currentProfile.occupation)}</div>
        <div class="typing-indicator">
            <span></span><span></span><span></span>
        </div>
    `;
    elements.chatMessages.appendChild(indicator);
    elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight;
}

// 移除加载指示器
function removeTypingIndicator() {
    const indicator = document.getElementById('typing-indicator');
    if (indicator) {
        indicator.remove();
    }
}

// 发送消息
async function sendMessage() {
    const message = elements.messageInput.value.trim();
    if (!message || isLoading || !currentSession) return;
    
    isLoading = true;
    elements.sendBtn.disabled = true;
    elements.messageInput.value = '';
    
    // 添加PM消息
    addMessage('pm', message);
    
    // 显示加载指示器
    addTypingIndicator();
    
    try {
        const response = await fetch(`/api/session/${currentSession}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message })
        });
        
        const data = await safeReadJson(response);
        
        // 移除加载指示器
        removeTypingIndicator();
        
        if (response.ok) {
            // 检查是否是API错误消息
            if (data.response && data.response.startsWith('[') && data.response.includes('错误')) {
                addMessage('user', `（系统提示：${data.response}，请重试）`);
            } else {
                // 添加用户回复
                addMessage('user', data.response, data.inner_thought, data.trust_change);
                
                // 更新状态
                updateStatus(data.status);
                
                // 检查是否结束
                if (data.is_ended) {
                    await showResult(data.end_reason);
                }
            }
        } else if (response.status === 404) {
            // 会话丢失
            addMessage('user', '（系统：会话已过期，请刷新页面重新开始）');
            alert('会话已过期，请刷新页面重新选择用户开始训练');
        } else {
            addMessage('user', `（系统：服务器错误 ${response.status}：${data.error || '请重试'}）`);
        }
    } catch (error) {
        console.error('发送消息失败:', error);
        removeTypingIndicator();
        addMessage('user', '（系统：网络连接失败，请检查网络后重试）');
    }
    
    isLoading = false;
    elements.sendBtn.disabled = false;
    elements.messageInput.focus();
}

// 显示评估结果
async function showResult(endReason) {
    // 设置结果标题
    const resultIcon = document.getElementById('result-icon');
    const resultTitle = document.getElementById('result-title');
    const resultSubtitle = document.getElementById('result-subtitle');
    
    const isSuccessLike = (endReason === 'success' || endReason === 'trust_full' || endReason === 'concerns_full');
    if (isSuccessLike) {
        resultIcon.textContent = '🎉';
        if (endReason === 'success') {
            resultTitle.textContent = '恭喜！成功说服用户开户！';
        } else if (endReason === 'trust_full') {
            resultTitle.textContent = '太棒了！信任度已满分';
        } else {
            resultTitle.textContent = '太棒了！已解答全部顾虑';
        }
        resultSubtitle.textContent = '查看你的表现评估';
    } else if (endReason === 'user_quit') {
        resultIcon.textContent = '😔';
        resultTitle.textContent = '用户失去了兴趣';
        resultSubtitle.textContent = '查看哪里可以改进';
    } else {
        resultIcon.textContent = '⏰';
        resultTitle.textContent = '对话轮数已达上限';
        resultSubtitle.textContent = '查看你的表现评估';
    }
    
    // 获取评估结果
    try {
        const response = await fetch(`/api/session/${currentSession}/evaluate`, {
            method: 'POST'
        });
        const evaluation = await response.json();
        // 评分标准：用于维度说明（来自配置，避免“编造标准”）
        await loadEvaluationCriteriaOnce();
        
        // 填充评估数据
        fillEvaluationData(evaluation, endReason);
        // 如果有“结束原因解释”，优先展示在副标题上（尤其是用户失去兴趣）
        const endExplain = (evaluation && evaluation.end_explanation) ? String(evaluation.end_explanation) : '';
        if (endExplain) {
            const resultSubtitle2 = document.getElementById('result-subtitle');
            if (resultSubtitle2) resultSubtitle2.textContent = endExplain;
        }
        
    } catch (error) {
        console.error('获取评估失败:', error);
    }
    
    // 切换到结果阶段
    switchStage('result');
}

// 填充评估数据
function fillEvaluationData(evaluation, endReason) {
    const stats = evaluation.stats || {};
    const scores = evaluation.scores || {};
    
    // 总分和等级
    const totalScore = evaluation.total_score || 0;
    document.getElementById('total-score').textContent = Math.round(totalScore);
    
    const grade = totalScore >= 90 ? 'S' : totalScore >= 80 ? 'A' : totalScore >= 70 ? 'B' : totalScore >= 60 ? 'C' : 'D';
    document.getElementById('score-grade').textContent = grade;

    // 得分拆解（规则分）
    const breakdown = evaluation.scoring_breakdown;
    const breakdownWrap = document.getElementById('score-breakdown');
    const breakdownList = document.getElementById('score-breakdown-list');
    if (breakdownWrap && breakdownList && breakdown && Array.isArray(breakdown.parts)) {
        breakdownWrap.style.display = 'block';
        breakdownList.innerHTML = breakdown.parts.map(p => {
            const delta = Number(p.delta || 0);
            const cls = delta >= 0 ? 'positive' : 'negative';
            const sign = delta > 0 ? `+${delta}` : `${delta}`;
            const name = p.name || '规则';
            return `<li class="score-breakdown-item">
                <span>${name}</span>
                <span class="score-breakdown-delta ${cls}">${sign}</span>
            </li>`;
        }).join('');
    } else if (breakdownWrap) {
        breakdownWrap.style.display = 'none';
    }
    
    // 统计数据
    document.getElementById('stat-turns').textContent = stats.turn_count || 0;
    document.getElementById('stat-trust').textContent = `${stats.final_trust || 0}/${stats.trust_threshold || 10}`;
    document.getElementById('stat-concerns').textContent = `${stats.concerns_addressed || 0}/${stats.total_concerns || 0}`;
    
    // 结果状态
    const statResultIcon = document.getElementById('stat-result-icon');
    const statResult = document.getElementById('stat-result');
    const isSuccessLike = (endReason === 'success' || endReason === 'trust_full' || endReason === 'concerns_full');
    if (isSuccessLike) {
        statResultIcon.textContent = '✅';
        statResult.textContent = '成功';
    } else {
        statResultIcon.textContent = '❌';
        statResult.textContent = '未成功';
    }
    
    // 维度评分（固定 5 维；缺失则显示 '-'，不默认补 0）
    const dimensionDefs = [
        { key: 'communication_skills', name: '沟通技巧' },
        { key: 'empathy', name: '同理心' },
        { key: 'problem_solving', name: '问题解决' },
        { key: 'persuasion', name: '说服力' },
        { key: 'professionalism', name: '专业度' },
    ];
    
    const dimensionsGrid = document.getElementById('dimensions-grid');
    const criteria = evaluationCriteriaCache || {};
    dimensionsGrid.innerHTML = dimensionDefs.map(({ key, name }) => {
        const raw = scores ? scores[key] : undefined;
        const val = Number(raw);
        const has = Number.isFinite(val);
        const desc = criteria?.[key]?.description ? String(criteria[key].description) : '';
        const width = has ? clamp(val, 0, 100) : 0;
        const scoreText = has ? String(Math.round(val)) : '-';
        return `
        <div class="dimension-item ${has ? '' : 'is-missing'}">
            <span class="dimension-name">
                ${name}
                ${desc ? `<span class="dimension-desc">${desc}</span>` : ``}
            </span>
            <div class="dimension-bar">
                <div class="dimension-progress" style="width: ${width}%"></div>
            </div>
            <span class="dimension-score">${scoreText}</span>
        </div>`;
    }).join('');

    // Radar 图（使用同一份 scores）
    renderRadarFromScores(scores);
    
    // 亮点
    const highlightsList = document.getElementById('highlights-list');
    const highlights = evaluation.highlights || ['完成了训练'];
    highlightsList.innerHTML = highlights.map(h => `<li>${h}</li>`).join('');
    
    // 改进建议
    const improvementsList = document.getElementById('improvements-list');
    const improvements = evaluation.improvements || ['继续练习'];
    improvementsList.innerHTML = improvements.map(i => `<li>${i}</li>`).join('');
    
    // 关键洞察
    const insightText = document.getElementById('insight-text');
    insightText.textContent = evaluation.key_insights || '持续练习可以提升用户感知能力';
    
    // 总体评价
    const commentText = document.getElementById('comment-text');
    commentText.textContent = evaluation.overall_comment || '继续加油！';
}

// 结束对话
async function endChat() {
    if (confirm('确定要结束当前对话吗？')) {
        await showResult('manual_end');
    }
}

// 重新开始当前用户
function retryCurrentProfile() {
    if (currentProfile) {
        startTraining(currentProfile.id, document.getElementById('retry-btn'));
    }
}

// 事件监听
document.addEventListener('DOMContentLoaded', () => {
    loadProfiles();
    loadTrainingOptions();

    // 启动训练取消按钮
    if (elements.startCancelBtn) {
        elements.startCancelBtn.addEventListener('click', () => {
            if (startAbortController) {
                try { startAbortController.abort(); } catch (_) {}
            }
            hideStartOverlay();
        });
    }

    // 用户卡片交互：点击卡片/查看档案打开 Drawer；点击开始训练直接开始
    if (elements.profilesList) {
        elements.profilesList.addEventListener('click', (e) => {
            const actionBtn = e.target.closest('button[data-action]');
            if (actionBtn) {
                e.stopPropagation();
                const id = Number(actionBtn.dataset.id);
                const action = actionBtn.dataset.action;
                if (action === 'start') startTraining(id, actionBtn);
                if (action === 'preview') openProfileDrawer(id);
                return;
            }

            const card = e.target.closest('.profile-select-card');
            if (card) {
                openProfileDrawer(Number(card.dataset.id));
            }
        });

        elements.profilesList.addEventListener('keydown', (e) => {
            const card = e.target.closest('.profile-select-card');
            if (!card) return;
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                openProfileDrawer(Number(card.dataset.id));
            }
        });
    }

    // Drawer 关闭
    const closeDrawerHandlers = [elements.drawerOverlay, elements.drawerCloseBtn, elements.drawerCancelBtn].filter(Boolean);
    closeDrawerHandlers.forEach(el => el.addEventListener('click', closeProfileDrawer));
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && document.body.classList.contains('drawer-open')) {
            closeProfileDrawer();
        }
    });

    // Drawer 开始训练
    if (elements.drawerStartBtn) {
        elements.drawerStartBtn.addEventListener('click', () => {
            if (!lastDrawerProfileId) return;
            startTraining(lastDrawerProfileId, elements.drawerStartBtn);
            closeProfileDrawer();
        });
    }

    // 一键随机开局
    if (elements.quickStartBtn) {
        elements.quickStartBtn.disabled = true; // 等 profiles 加载完再启用
        elements.quickStartBtn.addEventListener('click', () => {
            if (!profilesCache || profilesCache.length === 0) return;
            const idx = Math.floor(Math.random() * profilesCache.length);
            const p = profilesCache[idx];
            startTraining(p.id, elements.quickStartBtn);
        });
    }
    
    // 发送按钮点击
    elements.sendBtn.addEventListener('click', sendMessage);
    
    // 结束对话按钮
    elements.endChatBtn.addEventListener('click', endChat);
    
    // 重试按钮
    document.getElementById('retry-btn').addEventListener('click', retryCurrentProfile);
    
    // 输入框回车发送
    elements.messageInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });
    
    // 自动调整输入框高度
    elements.messageInput.addEventListener('input', function() {
        this.style.height = 'auto';
        this.style.height = Math.min(this.scrollHeight, 150) + 'px';
    });

    // Radar 图在窗口尺寸变化时重绘（仅当有数据）
    window.addEventListener('resize', () => {
        if (!lastRadarData) return;
        if (radarResizeTimer) clearTimeout(radarResizeTimer);
        radarResizeTimer = setTimeout(() => {
            const canvas = document.getElementById('radar-canvas');
            if (!canvas) return;
            drawRadarChart(canvas, lastRadarData.labels, lastRadarData.values);
        }, 120);
    });
});
