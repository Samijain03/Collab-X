(() => {
    const state = {
        chatSocket: null,
        workspaceSocket: null,
        workspaceFiles: new Map(),
        activeWorkspaceFile: null,
        workspaceSaveTimer: null,
        chatUI: null,
        workspaceUI: null,
    };

    document.addEventListener('DOMContentLoaded', () => {
        setupSidebarNavigation();
        setupSearchFilter();
        initializeDashboard();
    });

    function initializeDashboard() {
        cleanupRealtime();

        const chatContainer = document.querySelector('.chat-container');
        if (!chatContainer) {
            return;
        }

        state.chatContainer = chatContainer;
        state.botAvatar = chatContainer.dataset.botAvatar || '';

        const elements = gatherElements(chatContainer);

        scrollToBottom(elements.chatMessages);
        setupMobileSidebar(elements);
        setupEmojiPicker(elements);
        setupAttachmentUploads(elements);
        setupChatSocket(elements);
        setupChatForm(elements);
        setupMessageActions(elements);
        setupWorkspaceToggle(elements);
        setupWorkspaceModule(elements);
    }

    function gatherElements(container) {
        return {
            container,
            chatMessages: document.getElementById('chat-messages'),
            chatForm: document.getElementById('chat-form'),
            messageInput: document.getElementById('message-input'),
            mobileToggle: document.getElementById('mobileToggle'),
            mobileOverlay: document.getElementById('mobileOverlay'),
            sidebar: document.getElementById('sidebar'),
            attachmentBtn: document.getElementById('attachment-btn'),
            attachmentInput: document.getElementById('attachment-input'),
            attachmentStatus: document.getElementById('attachment-status'),
            emojiBtn: document.getElementById('emoji-btn'),
            chatType: container.dataset.chatType || '',
            chatId: container.dataset.chatId || '',
            workspaceKey: container.dataset.workspaceKey || '',
            currentUsername: container.dataset.currentUsername || '',
            uploadUrl: document.getElementById('chat-form')?.dataset.uploadUrl || '',
            workspacePanel: document.getElementById('workspacePanel'),
            workspaceList: document.getElementById('workspace-file-list'),
            workspaceEditor: document.getElementById('workspace-editor'),
            workspaceActive: document.getElementById('workspace-active-file'),
            workspaceLangBadge: document.getElementById('workspace-language'),
            workspaceRunBtn: document.getElementById('workspace-run-btn'),
            workspaceDownloadBtn: document.getElementById('workspace-download-btn'),
            workspaceRenameBtn: document.getElementById('workspace-rename-btn'),
            workspaceDeleteBtn: document.getElementById('workspace-delete-btn'),
            workspaceConsole: document.getElementById('workspace-console'),
            workspaceOutputMeta: document.getElementById('workspace-output-meta'),
            workspacePreview: document.getElementById('workspace-preview'),
            workspaceCreateButtons: document.querySelectorAll('[data-workspace-create]'),
        };
    }

    function cleanupRealtime() {
        if (state.chatSocket) {
            state.chatSocket.close();
            state.chatSocket = null;
        }
        if (state.workspaceSocket) {
            state.workspaceSocket.close();
            state.workspaceSocket = null;
        }
        state.workspaceFiles = new Map();
        state.activeWorkspaceFile = null;
        if (state.workspaceSaveTimer) {
            clearTimeout(state.workspaceSaveTimer);
            state.workspaceSaveTimer = null;
        }
        state.chatUI = null;
        state.workspaceUI = null;
    }

    function setupSidebarNavigation() {
        const sidebar = document.getElementById('sidebar');
        if (!sidebar) return;

        sidebar.addEventListener('click', (event) => {
            const link = event.target.closest('.contact-item[data-dynamic="true"]');
            if (!link) return;

            event.preventDefault();
            const url = link.getAttribute('href');
            if (!url) return;

            sidebar.querySelectorAll('.contact-item.active').forEach(item => item.classList.remove('active'));
            link.classList.add('active');

            loadConversation(url);
        });
    }

    function loadConversation(url) {
        cleanupRealtime();
        const indicator = document.getElementById('chatLoadingIndicator');
        showChatLoading(indicator, true);

        fetch(url, {
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        })
            .then(response => {
                if (!response.ok) {
                    throw new Error('Failed to load conversation');
                }
                return response.json();
            })
            .then(data => {
                replaceSection('chatArea', data.chat_html);
                replaceSection('workspacePanel', data.workspace_html);

                const container = document.querySelector('.chat-container');
                if (container) {
                    container.dataset.chatType = data.chat_type || '';
                    container.dataset.chatId = data.chat_id || '';
                    container.dataset.workspaceKey = data.workspace_key || '';
                }

                initializeDashboard();
            })
            .catch(error => {
                console.error(error);
                window.location.href = url;
            })
            .finally(() => showChatLoading(indicator, false));
    }

    function replaceSection(id, html) {
        if (!html) return;
        const target = document.getElementById(id);
        if (!target) return;
        const template = document.createElement('template');
        template.innerHTML = html.trim();
        const content = template.content.firstElementChild;
        if (content) {
            target.replaceWith(content);
        }
    }

    function showChatLoading(indicator, show) {
        if (!indicator) return;
        indicator.classList.toggle('d-none', !show);
    }

    function setupSearchFilter() {
        const input = document.getElementById('contact-search-input');
        if (!input || input.dataset.bound === 'true') return;

        input.addEventListener('input', () => {
            const filter = input.value.toLowerCase();
            document.querySelectorAll('.contact-list .contact-item').forEach(item => {
                const name = item.querySelector('.contact-info h6')?.textContent.toLowerCase() || '';
                const username = item.querySelector('.contact-info small')?.textContent.toLowerCase() || '';
                item.style.display = (name + username).includes(filter) ? 'flex' : 'none';
            });
        });

        input.dataset.bound = 'true';
    }

    function setupMobileSidebar({ mobileToggle, mobileOverlay, sidebar }) {
        if (!mobileToggle || mobileToggle.dataset.bound === 'true' || !sidebar) return;

        mobileToggle.addEventListener('click', () => {
            sidebar.classList.toggle('show');
            mobileOverlay?.classList.toggle('show');
        });

        mobileOverlay?.addEventListener('click', () => {
            sidebar.classList.remove('show');
            mobileOverlay.classList.remove('show');
        });

        mobileToggle.dataset.bound = 'true';
    }

    function setupEmojiPicker({ emojiBtn, messageInput }) {
        if (!emojiBtn) return;

        if (!window.EmojiButton) {
            emojiBtn.disabled = true;
            return;
        }

        const picker = new EmojiButton({
            position: 'top-end',
            theme: 'dark'
        });

        picker.on('emoji', selection => {
            if (messageInput) {
                messageInput.value += selection.emoji;
                messageInput.focus();
            }
        });

        emojiBtn.addEventListener('click', () => picker.togglePicker(emojiBtn));
    }

    function setupAttachmentUploads({ attachmentBtn, attachmentInput, attachmentStatus, uploadUrl, messageInput }) {
        if (!attachmentBtn) return;

        if (!uploadUrl) {
            attachmentBtn.disabled = true;
            return;
        }

        attachmentBtn.addEventListener('click', () => attachmentInput?.click());
        attachmentInput?.addEventListener('change', async (event) => {
            const file = event.target.files?.[0];
            if (!file) return;

            const caption = messageInput?.value.trim() || '';
            toggleAttachmentStatus(attachmentStatus, 'Uploading attachment...', 'remove');

            const formData = new FormData();
            formData.append('file', file);
            formData.append('caption', caption);

            try {
                const response = await fetch(uploadUrl, {
                    method: 'POST',
                    headers: { 'X-CSRFToken': getCsrfToken() },
                    body: formData
                });

                if (!response.ok) {
                    throw new Error(await response.text());
                }

                await response.json();
                toggleAttachmentStatus(attachmentStatus, 'Attachment sent', 'success');
                if (messageInput) messageInput.value = '';
            } catch (error) {
                console.error(error);
                toggleAttachmentStatus(attachmentStatus, 'Upload failed', 'danger');
            } finally {
                if (attachmentInput) attachmentInput.value = '';
                setTimeout(() => toggleAttachmentStatus(attachmentStatus, '', 'hide'), 4000);
            }
        });
    }

    function toggleAttachmentStatus(element, text, state) {
        if (!element) return;
        element.classList.remove('d-none', 'text-danger', 'text-success');
        if (state === 'success') {
            element.classList.add('text-success');
        } else if (state === 'danger') {
            element.classList.add('text-danger');
        } else if (state === 'hide') {
            element.classList.add('d-none');
            element.textContent = '';
            return;
        }
        element.textContent = text;
    }

    function setupChatSocket(elements) {
        const { chatType, chatId, chatMessages, currentUsername } = elements;
        if (!chatType || !chatId) return;

        state.chatUI = {
            chatMessages,
            chatType,
            currentUsername
        };

        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = chatType === '1on1'
            ? `${wsProtocol}//${window.location.host}/ws/chat/${chatId}/`
            : `${wsProtocol}//${window.location.host}/ws/group/${chatId}/`;

        state.chatSocket = new WebSocket(wsUrl);
        state.chatSocket.onmessage = (event) => handleChatMessage(event);
        state.chatSocket.onclose = (event) => console.warn('Chat socket closed', event.reason);
    }

    function handleChatMessage(event) {
        if (!state.chatUI || !state.chatUI.chatMessages) return;
        const data = JSON.parse(event.data);
        const container = state.chatUI.chatMessages;

        if (data.type === 'chat_message') {
            const bubble = createMessageBubble({
                content: data.content,
                timestamp: data.timestamp,
                isSent: data.sender_username === state.chatUI.currentUsername,
                senderDisplayName: state.chatUI.chatType === 'group' ? data.sender_display_name : null,
                messageId: data.message_id,
                attachment: {
                    url: data.attachment_url,
                    name: data.attachment_name
                }
            });
            container.appendChild(bubble);
            scrollToBottom(container);
        } else if (data.type === 'message_deleted') {
            const bubble = container.querySelector(`.message-bubble[data-message-id='${data.message_id}']`);
            if (bubble) {
                bubble.innerHTML = `
                    <p class="fst-italic" style="opacity: 0.7;">This message was deleted.</p>
                    <span class="message-time"></span>
                `;
            }
        } else if (data.type === 'bot_message') {
            handleBotMessage(data);
        }
    }

    function handleBotMessage(data) {
        if (!state.chatUI || !state.chatUI.chatMessages) return;
        const container = state.chatUI.chatMessages;

        if (data.status === 'thinking') {
            const bubble = createBotMessageBubble({
                content: data.content,
                senderUsername: data.sender_username,
                jumpId: null,
                requestId: data.request_id
            });
            container.appendChild(bubble);
        } else if (data.status === 'complete') {
            const existing = document.getElementById(`bot-response-${data.request_id}`);
            if (existing) {
                const contentP = existing.querySelector(`#bot-content-${data.request_id}`);
                if (contentP) {
                    contentP.textContent = data.content;
                }
                if (data.jump_id) {
                    const jumpContainer = existing.querySelector(`#bot-jump-${data.request_id}`);
                    if (jumpContainer) {
                        jumpContainer.innerHTML = '';
                        const jumpBtn = document.createElement('button');
                        jumpBtn.className = 'jump-btn';
                        jumpBtn.textContent = 'Jump to message';
                        jumpBtn.dataset.jumpId = data.jump_id;
                        jumpContainer.appendChild(jumpBtn);
                    }
                }
            }
        }
        scrollToBottom(container);
    }

    function setupChatForm({ chatForm, messageInput }) {
        if (!chatForm || !messageInput) return;

        chatForm.addEventListener('submit', (event) => {
            event.preventDefault();
            const message = messageInput.value.trim();
            if (message && state.chatSocket) {
                state.chatSocket.send(JSON.stringify({
                    type: 'chat_message',
                    message
                }));
                messageInput.value = '';
            }
        });
    }

    function setupMessageActions({ chatMessages }) {
        if (!chatMessages) return;

        chatMessages.addEventListener('click', (event) => {
            const deleteBtn = event.target.closest('.delete-msg-btn');
            if (deleteBtn) {
                event.preventDefault();
                const bubble = deleteBtn.closest('.message-bubble');
                const messageId = bubble?.dataset.messageId;
                if (messageId && state.chatSocket && confirm('Delete this message?')) {
                    state.chatSocket.send(JSON.stringify({
                        type: 'delete_message',
                        message_id: messageId
                    }));
                }
                return;
            }

            const jumpBtn = event.target.closest('.jump-btn');
            if (jumpBtn) {
                event.preventDefault();
                const jumpId = jumpBtn.dataset.jumpId;
                if (!jumpId) return;
                const target = document.querySelector(`.message-bubble[data-message-id='${jumpId}']`);
                if (target) {
                    target.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    target.classList.add('highlight');
                    setTimeout(() => target.classList.remove('highlight'), 2000);
                } else {
                    alert('Message not found in current view');
                }
            }
        });
    }

    function setupWorkspaceToggle({ workspacePanel }) {
        if (!workspacePanel) return;
        const toggleBtn = workspacePanel.querySelector('#workspaceToggleBtn');
        if (!toggleBtn) return;

        const storageKey = 'collab_x_workspace_collapsed';
        const applyState = (collapsed) => {
            workspacePanel.classList.toggle('collapsed', collapsed);
            toggleBtn.setAttribute('aria-expanded', (!collapsed).toString());
            toggleBtn.innerHTML = collapsed ? '<i class="bi bi-chevron-left"></i>' : '<i class="bi bi-chevron-right"></i>';
        };

        const stored = localStorage.getItem(storageKey) === 'true';
        if (stored) applyState(true);

        toggleBtn.addEventListener('click', () => {
            const collapsed = !workspacePanel.classList.contains('collapsed');
            applyState(collapsed);
            localStorage.setItem(storageKey, collapsed ? 'true' : 'false');
        });
    }

    function setupWorkspaceModule(elements) {
        const {
            workspaceKey,
            workspaceList,
            workspaceEditor,
            workspaceActive,
            workspaceLangBadge,
            workspaceRunBtn,
            workspaceDownloadBtn,
            workspaceRenameBtn,
            workspaceDeleteBtn,
            workspaceConsole,
            workspaceOutputMeta,
            workspacePreview,
            workspaceCreateButtons
        } = elements;

        if (!workspaceKey) {
            return;
        }

        state.workspaceUI = {
            workspaceList,
            workspaceEditor,
            workspaceActive,
            workspaceLangBadge,
            workspaceRunBtn,
            workspaceDownloadBtn,
            workspaceRenameBtn,
            workspaceDeleteBtn,
            workspaceConsole,
            workspaceOutputMeta,
            workspacePreview
        };

        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${wsProtocol}//${window.location.host}/ws/workspace/${workspaceKey}/`;
        state.workspaceSocket = new WebSocket(wsUrl);

        state.workspaceSocket.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.type === 'workspace_bootstrap') {
                state.workspaceFiles = new Map();
                data.files.forEach(file => state.workspaceFiles.set(file.id, file));
                renderWorkspaceList();
            } else if (data.type === 'workspace_event') {
                handleWorkspaceEvent(data);
            }
        };

        workspaceCreateButtons.forEach(btn => {
            btn.addEventListener('click', () => {
                const language = btn.dataset.workspaceCreate;
                const defaultName = language === 'python' ? 'main.py' : 'index.html';
                const name = prompt(`Name your ${language.toUpperCase()} file:`, defaultName);
                if (name && state.workspaceSocket) {
                    state.workspaceSocket.send(JSON.stringify({
                        action: 'create_file',
                        language,
                        name: name.trim()
                    }));
                }
            });
        });

        workspaceList?.addEventListener('click', (event) => {
            const item = event.target.closest('.workspace-file-item');
            if (!item) return;
            setActiveWorkspaceFile(Number(item.dataset.fileId));
        });

        workspaceRenameBtn?.addEventListener('click', () => {
            if (!state.activeWorkspaceFile || !state.workspaceSocket) return;
            const currentName = state.workspaceFiles.get(state.activeWorkspaceFile)?.name;
            const newName = prompt('Rename file', currentName);
            if (newName && newName.trim() !== currentName) {
                state.workspaceSocket.send(JSON.stringify({
                    action: 'rename_file',
                    file_id: state.activeWorkspaceFile,
                    name: newName.trim()
                }));
            }
        });

        workspaceDeleteBtn?.addEventListener('click', () => {
            if (!state.activeWorkspaceFile || !state.workspaceSocket) return;
            if (confirm('Delete this file for everyone?')) {
                state.workspaceSocket.send(JSON.stringify({
                    action: 'delete_file',
                    file_id: state.activeWorkspaceFile
                }));
            }
        });

        workspaceEditor?.addEventListener('input', () => {
            if (!state.activeWorkspaceFile || !state.workspaceSocket) return;
            if (state.workspaceSaveTimer) {
                clearTimeout(state.workspaceSaveTimer);
            }
            state.workspaceSaveTimer = setTimeout(() => {
                state.workspaceSocket?.send(JSON.stringify({
                    action: 'update_content',
                    file_id: state.activeWorkspaceFile,
                    content: workspaceEditor.value
                }));
            }, 600);
        });

        workspaceRunBtn?.addEventListener('click', () => {
            if (!state.activeWorkspaceFile || !state.workspaceSocket) return;
            state.workspaceSocket.send(JSON.stringify({
                action: 'run_file',
                file_id: state.activeWorkspaceFile
            }));
        });

        workspaceDownloadBtn?.addEventListener('click', () => {
            if (!state.activeWorkspaceFile) return;
            const file = state.workspaceFiles.get(state.activeWorkspaceFile);
            if (!file) return;
            const blob = new Blob([file.content], { type: 'text/plain' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = file.name;
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(url);
        });
    }

    function handleWorkspaceEvent(payload) {
        const { workspaceEditor, workspaceActive, workspaceLangBadge } = state.workspaceUI || {};
        const file = payload.file;

        switch (payload.event) {
            case 'file_created':
            case 'file_updated':
            case 'file_renamed':
                state.workspaceFiles.set(file.id, file);
                if (state.activeWorkspaceFile === file.id && workspaceEditor) {
                    workspaceEditor.value = file.content;
                    if (workspaceActive) workspaceActive.textContent = file.name;
                    if (workspaceLangBadge) {
                        workspaceLangBadge.textContent = file.language.toUpperCase();
                        workspaceLangBadge.classList.remove('d-none');
                    }
                }
                renderWorkspaceList();
                break;
            case 'file_deleted':
                state.workspaceFiles.delete(payload.file_id);
                if (state.activeWorkspaceFile === payload.file_id) {
                    resetWorkspaceEditor();
                }
                renderWorkspaceList();
                break;
            case 'run_result':
                updateRunOutput(payload);
                break;
        }
    }

    function renderWorkspaceList() {
        const { workspaceList } = state.workspaceUI || {};
        if (!workspaceList) return;

        workspaceList.innerHTML = '';
        if (state.workspaceFiles.size === 0) {
            workspaceList.innerHTML = '<div class="p-3 text-center text-muted small"><i class="bi bi-files"></i> No files yet</div>';
            return;
        }

        const fragment = document.createDocumentFragment();
        Array.from(state.workspaceFiles.values())
            .sort((a, b) => a.name.localeCompare(b.name))
            .forEach(file => {
                const item = document.createElement('div');
                item.className = 'workspace-file-item';
                if (state.activeWorkspaceFile === file.id) {
                    item.classList.add('active');
                }
                item.dataset.fileId = file.id;
                item.innerHTML = `
                    <span><i class="bi bi-file-earmark-code me-2"></i>${file.name}</span>
                    <small class="text-uppercase text-muted">${file.language}</small>
                `;
                fragment.appendChild(item);
            });
        workspaceList.appendChild(fragment);
    }

    function setActiveWorkspaceFile(fileId) {
        const file = state.workspaceFiles.get(fileId);
        if (!file || !state.workspaceUI) return;
        const {
            workspaceEditor,
            workspaceActive,
            workspaceLangBadge,
            workspaceRunBtn,
            workspaceDownloadBtn,
            workspaceRenameBtn,
            workspaceDeleteBtn
        } = state.workspaceUI;

        state.activeWorkspaceFile = fileId;

        if (workspaceEditor) {
            workspaceEditor.disabled = false;
            workspaceEditor.value = file.content;
        }
        if (workspaceActive) workspaceActive.textContent = file.name;
        if (workspaceLangBadge) {
            workspaceLangBadge.textContent = file.language.toUpperCase();
            workspaceLangBadge.classList.remove('d-none');
        }
        [workspaceRunBtn, workspaceDownloadBtn, workspaceRenameBtn, workspaceDeleteBtn].forEach(btn => {
            if (btn) btn.disabled = false;
        });

        renderWorkspaceList();
    }

    function resetWorkspaceEditor() {
        const {
            workspaceEditor,
            workspaceActive,
            workspaceLangBadge,
            workspaceRunBtn,
            workspaceDownloadBtn,
            workspaceRenameBtn,
            workspaceDeleteBtn,
            workspaceConsole,
            workspaceOutputMeta,
            workspacePreview
        } = state.workspaceUI || {};

        state.activeWorkspaceFile = null;
        if (workspaceEditor) {
            workspaceEditor.disabled = true;
            workspaceEditor.value = '';
        }
        if (workspaceActive) workspaceActive.textContent = 'Select a file';
        if (workspaceLangBadge) workspaceLangBadge.classList.add('d-none');
        [workspaceRunBtn, workspaceDownloadBtn, workspaceRenameBtn, workspaceDeleteBtn].forEach(btn => {
            if (btn) btn.disabled = true;
        });
        if (workspaceConsole) workspaceConsole.textContent = 'Select a file and press Run to see output.';
        if (workspaceOutputMeta) workspaceOutputMeta.textContent = '';
        if (workspacePreview) {
            workspacePreview.classList.add('d-none');
            workspacePreview.removeAttribute('srcdoc');
        }
    }

    function updateRunOutput(payload) {
        const {
            workspaceConsole,
            workspaceOutputMeta,
            workspacePreview
        } = state.workspaceUI || {};
        if (!workspaceConsole || !workspaceOutputMeta || !workspacePreview) return;

        const { result, language, requested_by } = payload;
        if (language === 'html') {
            workspacePreview.classList.remove('d-none');
            workspacePreview.srcdoc = result.html || '';
            workspaceConsole.textContent = 'Rendered HTML preview below.';
        } else {
            workspacePreview.classList.add('d-none');
            workspacePreview.removeAttribute('srcdoc');
            const stdout = result.stdout || '';
            const stderr = result.stderr || '';
            workspaceConsole.textContent = `${stdout}${stderr ? `\n⚠️ ${stderr}` : ''}`.trim() || '(no output)';
        }
        workspaceOutputMeta.textContent = `${language.toUpperCase()} • requested by ${requested_by}`;
    }

    function createMessageBubble({ content, timestamp, isSent, senderDisplayName, messageId, attachment }) {
        const bubble = document.createElement('div');
        bubble.className = `message-bubble ${isSent ? 'sent' : 'received'}`;
        bubble.dataset.messageId = messageId;

        if (senderDisplayName && !isSent) {
            const sender = document.createElement('small');
            sender.className = 'fw-bold d-block mb-1';
            sender.style.color = 'var(--primary-light)';
            sender.textContent = senderDisplayName;
            bubble.appendChild(sender);
        }

        if (content) {
            const contentNode = document.createElement('p');
            contentNode.textContent = content;
            bubble.appendChild(contentNode);
        }

        if (attachment?.url) {
            const attachmentCard = document.createElement('div');
            attachmentCard.className = 'attachment-card';
            attachmentCard.innerHTML = `
                <i class="bi bi-paperclip"></i>
                <div class="flex-grow-1">
                    <strong>${attachment.name || 'Attachment'}</strong>
                </div>
                <a class="btn btn-sm btn-outline-light" href="${attachment.url}" download>
                    <i class="bi bi-download me-1"></i>Download
                </a>
            `;
            bubble.appendChild(attachmentCard);
        }

        if (isSent) {
            const deleteBtn = document.createElement('button');
            deleteBtn.className = 'btn btn-danger btn-sm delete-msg-btn float-end';
            deleteBtn.title = 'Delete message';
            deleteBtn.innerHTML = '<i class="bi bi-trash"></i>';
            bubble.appendChild(deleteBtn);
        }

        const time = document.createElement('span');
        time.className = 'message-time';
        time.textContent = timestamp;
        bubble.appendChild(time);

        return bubble;
    }

    function createBotMessageBubble({ content, senderUsername, jumpId, requestId }) {
        const bubble = document.createElement('div');
        bubble.className = 'message-bubble bot';
        bubble.id = `bot-response-${requestId}`;

        const avatar = document.createElement('img');
        avatar.className = 'bot-avatar';
        avatar.src = state.botAvatar || '';
        avatar.alt = 'Bot';
        bubble.appendChild(avatar);

        const wrapper = document.createElement('div');
        wrapper.className = 'bot-content-wrapper';

        const header = document.createElement('div');
        header.className = 'bot-header';
        header.innerHTML = `<i class="bi bi-robot"></i>${senderUsername}`;
        wrapper.appendChild(header);

        const contentP = document.createElement('p');
        contentP.id = `bot-content-${requestId}`;
        contentP.textContent = content;
        wrapper.appendChild(contentP);

        const jumpContainer = document.createElement('div');
        jumpContainer.id = `bot-jump-${requestId}`;
        if (jumpId) {
            const jumpBtn = document.createElement('button');
            jumpBtn.className = 'jump-btn';
            jumpBtn.textContent = 'Jump to message';
            jumpBtn.dataset.jumpId = jumpId;
            jumpContainer.appendChild(jumpBtn);
        }
        wrapper.appendChild(jumpContainer);

        bubble.appendChild(wrapper);
        return bubble;
    }

    function scrollToBottom(container) {
        if (!container) return;
        container.scrollTop = container.scrollHeight;
    }

    function getCsrfToken() {
        const match = document.cookie.match(/csrftoken=([^;]+)/);
        return match ? match[1] : '';
    }
})();

