(() => {
    const state = {
        chatSocket: null,
        workspaceSocket: null,
        workspaceNodes: new Map(),
        workspaceTree: null,
        activeWorkspaceNode: null,
        workspaceSaveTimer: null,
        expandedFolders: new Set(),
        chatUI: null,
        workspaceUI: null,
        workspaceContent: '', // Track current content for delta calculation
        workspaceLastContent: '', // Last known content state
        workspaceCursors: new Map(), // Map of user_id -> cursor info
        workspaceUsers: new Map(), // Map of user_id -> user info
        workspaceIsApplyingRemote: false, // Flag to prevent feedback loops
        workspaceCursorUpdateTimer: null
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
            workspaceTree: document.getElementById('workspace-file-tree'),
            workspaceNewFileBtn: document.getElementById('workspace-new-file-btn'),
            workspaceNewFolderBtn: document.getElementById('workspace-new-folder-btn'),
            workspaceBatchBtn: document.getElementById('workspace-batch-btn'),
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
        state.workspaceNodes = new Map();
        state.workspaceTree = null;
        state.activeWorkspaceNode = null;
        state.expandedFolders.clear();
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

    function buildWorkspaceTree(nodes) {
        const nodeMap = new Map();
        const rootNodes = [];

        nodes.forEach(node => {
            nodeMap.set(node.id, { ...node, children: [] });
        });

        nodes.forEach(node => {
            const nodeObj = nodeMap.get(node.id);
            if (node.parent_id === null || node.parent_id === undefined) {
                rootNodes.push(nodeObj);
            } else {
                const parent = nodeMap.get(node.parent_id);
                if (parent) {
                    parent.children.push(nodeObj);
                } else {
                    rootNodes.push(nodeObj);
                }
            }
        });

        function sortChildren(children) {
            return children.sort((a, b) => {
                if (a.node_type === 'folder' && b.node_type === 'file') return -1;
                if (a.node_type === 'file' && b.node_type === 'folder') return 1;
                return a.name.localeCompare(b.name);
            });
        }

        function sortTree(nodes) {
            sortChildren(nodes);
            nodes.forEach(node => {
                if (node.children.length > 0) {
                    sortTree(node.children);
                }
            });
        }

        sortTree(rootNodes);
        return { nodeMap, rootNodes };
    }

    function renderWorkspaceTree() {
        const { workspaceTree } = state.workspaceUI || {};
        if (!workspaceTree) return;

        workspaceTree.innerHTML = '';

        if (!state.workspaceTree || state.workspaceTree.rootNodes.length === 0) {
            workspaceTree.innerHTML = '<div class="p-3 text-center text-muted small"><i class="bi bi-files"></i> No files yet</div>';
            return;
        }

        function createNodeElement(node, depth = 0) {
            const isFolder = node.node_type === 'folder';
            const isFile = node.node_type === 'file';
            const isExpanded = state.expandedFolders.has(node.id);
            const isActive = state.activeWorkspaceNode === node.id;

            const nodeEl = document.createElement('div');
            nodeEl.className = `workspace-tree-node ${node.node_type}${isActive ? ' active' : ''}${isExpanded ? ' expanded' : ''}`;
            nodeEl.dataset.nodeId = node.id;
            nodeEl.style.paddingLeft = `${depth * 1.25}rem`;

            const iconEl = document.createElement('div');
            iconEl.className = 'workspace-tree-node-icon';

            if (isFolder) {
                iconEl.innerHTML = isExpanded ? '<i class="bi bi-folder2-open"></i>' : '<i class="bi bi-folder2"></i>';
            } else {
                const lang = node.language || 'text';
                const iconMap = {
                    python: 'bi-filetype-py',
                    html: 'bi-filetype-html',
                    javascript: 'bi-filetype-js',
                    css: 'bi-filetype-css',
                    json: 'bi-filetype-json',
                    markdown: 'bi-filetype-md',
                    text: 'bi-file-earmark-text'
                };
                iconEl.innerHTML = `<i class="bi ${iconMap[lang] || 'bi-file-earmark'}"></i>`;
            }

            const nameEl = document.createElement('span');
            nameEl.className = 'workspace-tree-node-name';
            nameEl.textContent = node.name;
            nameEl.title = node.full_path || node.name;

            nodeEl.appendChild(iconEl);
            nodeEl.appendChild(nameEl);

            if (isFolder && node.children.length > 0) {
                const childrenEl = document.createElement('div');
                childrenEl.className = 'workspace-tree-node-children';
                node.children.forEach(child => {
                    childrenEl.appendChild(createNodeElement(child, depth + 1));
                });
                nodeEl.appendChild(childrenEl);
            }

            return nodeEl;
        }

        const fragment = document.createDocumentFragment();
        state.workspaceTree.rootNodes.forEach(node => {
            fragment.appendChild(createNodeElement(node));
        });

        workspaceTree.appendChild(fragment);
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

        toggleBtn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            const isCurrentlyCollapsed = workspacePanel.classList.contains('collapsed');
            const newState = !isCurrentlyCollapsed;
            applyState(newState);
            localStorage.setItem(storageKey, newState ? 'true' : 'false');
        });
    }

    function setupWorkspaceModule(elements) {
        const {
            workspaceKey,
            workspaceTree,
            workspaceNewFileBtn,
            workspaceNewFolderBtn,
            workspaceBatchBtn,
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
            workspaceTree,
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

        // Load expanded folders from localStorage
        const savedExpanded = localStorage.getItem(`workspace_expanded_${workspaceKey}`);
        if (savedExpanded) {
            try {
                state.expandedFolders = new Set(JSON.parse(savedExpanded));
            } catch (e) {
                state.expandedFolders = new Set();
            }
        }

        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${wsProtocol}//${window.location.host}/ws/workspace/${workspaceKey}/`;
        state.workspaceSocket = new WebSocket(wsUrl);

        state.workspaceSocket.onopen = () => {
            // Request file list when connected
            state.workspaceSocket.send(JSON.stringify({
                type: 'list_files'
            }));
        };

        state.workspaceSocket.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.type === 'workspace_bootstrap') {
                state.workspaceNodes = new Map();
                data.nodes.forEach(node => state.workspaceNodes.set(node.id, node));
                state.workspaceTree = buildWorkspaceTree(Array.from(state.workspaceNodes.values()));
                renderWorkspaceTree();
            } else if (data.type === 'workspace_event') {
                handleWorkspaceEvent(data);
            } else if (data.type === 'file_update') {
                handleFileUpdate(data);
            } else if (data.type === 'cursor_update') {
                handleCursorUpdate(data);
            } else if (data.type === 'file_focus') {
                handleFileFocus(data);
            } else if (data.type === 'user_joined') {
                handleUserJoined(data);
            } else if (data.type === 'user_left') {
                handleUserLeft(data);
            } else if (data.type === 'file_list') {
                // Handle file list updates
                state.workspaceNodes = new Map();
                data.files.forEach(node => {
                    // Ensure content is initialized
                    if (!node.content) node.content = '';
                    state.workspaceNodes.set(node.id, node);
                });
                state.workspaceTree = buildWorkspaceTree(Array.from(state.workspaceNodes.values()));
                renderWorkspaceTree();
            } else if (data.type === 'file_content') {
                // Handle file content response
                const nodeId = data.node_id;
                if (nodeId) {
                    // Update node content in our map
                    const node = state.workspaceNodes.get(nodeId);
                    if (node) {
                        node.content = data.content;
                    }
                    
                    // If this is the active file, update editor
                    if (nodeId === state.activeWorkspaceNode) {
                        const { workspaceEditor } = state.workspaceUI || {};
                        if (workspaceEditor) {
                            state.workspaceIsApplyingRemote = true;
                            workspaceEditor.value = data.content;
                            state.workspaceContent = data.content;
                            state.workspaceLastContent = data.content;
                            state.workspaceIsApplyingRemote = false;
                        }
                    }
                }
            } else if (data.type === 'execution_result') {
                // Handle code execution result
                const { workspaceConsole, workspaceOutputMeta } = state.workspaceUI || {};
                if (workspaceConsole && workspaceOutputMeta) {
                    const output = data.output || '(no output)';
                    workspaceConsole.textContent = output;
                    workspaceOutputMeta.textContent = `${(data.language || 'python').toUpperCase()} • Execution Result`;
                }
            }
        };

        // Tree click handlers
        if (workspaceTree) {
            workspaceTree.addEventListener('click', (event) => {
                // Don't trigger if clicking on buttons
                if (event.target.closest('.workspace-tree-actions')) return;
                
                const nodeEl = event.target.closest('.workspace-tree-node');
                if (!nodeEl) return;

                const nodeId = Number(nodeEl.dataset.nodeId);
                const node = state.workspaceNodes.get(nodeId);
                if (!node) return;

                if (node.node_type === 'folder') {
                    // Toggle expand/collapse
                    if (state.expandedFolders.has(nodeId)) {
                        state.expandedFolders.delete(nodeId);
                    } else {
                        state.expandedFolders.add(nodeId);
                    }
                    const workspaceKey = elements.workspaceKey;
                    localStorage.setItem(`workspace_expanded_${workspaceKey}`, JSON.stringify(Array.from(state.expandedFolders)));
                    renderWorkspaceTree();
                } else {
                    // Select file
                    setActiveWorkspaceNode(nodeId);
                }
            });
        }

        // New file button
        if (workspaceNewFileBtn) {
            workspaceNewFileBtn.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                const name = prompt('Enter file name (e.g., main.py, index.html):', 'main.py');
                if (name && name.trim() && state.workspaceSocket) {
                    const fileName = name.trim();
                    state.workspaceSocket.send(JSON.stringify({
                        type: 'create_node',
                        name: fileName,
                        node_type: 'file',
                        parent_id: null
                    }));
                }
            });
        }

        // New folder button
        if (workspaceNewFolderBtn) {
            workspaceNewFolderBtn.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                const name = prompt('Enter folder name:', 'new-folder');
                if (name && name.trim() && state.workspaceSocket) {
                    const folderName = name.trim();
                    state.workspaceSocket.send(JSON.stringify({
                        type: 'create_node',
                        name: folderName,
                        node_type: 'folder',
                        parent_id: null
                    }));
                }
            });
        }

        // Batch create button
        if (workspaceBatchBtn) {
            workspaceBatchBtn.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                const input = prompt('Enter file paths (one per line):\nExample:\nbackend/app.py\nfrontend/index.html\nutils/helper.js');
                if (!input || !state.workspaceSocket) return;

                const paths = input.split('\n').map(p => p.trim()).filter(p => p);
                if (paths.length === 0) return;

                // Create files/folders one by one (backend doesn't support batch yet)
                paths.forEach(path => {
                    const isFolder = path.endsWith('/');
                    const name = isFolder ? path.slice(0, -1) : path;
                    if (name) {
                        state.workspaceSocket.send(JSON.stringify({
                            type: 'create_node',
                            name: name,
                            node_type: isFolder ? 'folder' : 'file',
                            parent_id: null
                        }));
                    }
                });
            });
        }

        // Legacy create buttons (for backward compatibility)
        if (workspaceCreateButtons && workspaceCreateButtons.length > 0) {
            workspaceCreateButtons.forEach(btn => {
                btn.addEventListener('click', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    if (btn.disabled) return;
                    const language = btn.dataset.workspaceCreate;
                    const defaultName = language === 'python' ? 'main.py' : 'index.html';
                    const name = prompt(`Name your ${language.toUpperCase()} file:`, defaultName);
                    if (name && name.trim() && state.workspaceSocket) {
                        state.workspaceSocket.send(JSON.stringify({
                            type: 'create_node',
                            name: name.trim(),
                            node_type: 'file',
                            parent_id: null
                        }));
                    }
                });
            });
        }

        if (workspaceRenameBtn) {
            workspaceRenameBtn.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                if (!state.activeWorkspaceNode || !state.workspaceSocket || workspaceRenameBtn.disabled) return;
                const node = state.workspaceNodes.get(state.activeWorkspaceNode);
                if (!node) return;
                const newName = prompt('Rename', node.name);
                if (newName && newName.trim() !== node.name) {
                    // Note: Rename functionality needs to be implemented in backend
                    alert('Rename functionality coming soon!');
                }
            });
        }

        if (workspaceDeleteBtn) {
            workspaceDeleteBtn.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                if (!state.activeWorkspaceNode || !state.workspaceSocket || workspaceDeleteBtn.disabled) return;
                const node = state.workspaceNodes.get(state.activeWorkspaceNode);
                if (!node) return;
                const confirmMsg = node.node_type === 'folder' 
                    ? 'Delete this folder and all its contents for everyone?'
                    : 'Delete this file for everyone?';
                if (confirm(confirmMsg)) {
                    state.workspaceSocket.send(JSON.stringify({
                        type: 'delete_node',
                        node_id: state.activeWorkspaceNode
                    }));
                }
            });
        }

        // Enhanced input handler with incremental updates
        if (workspaceEditor) {
            workspaceEditor.addEventListener('input', (e) => {
                if (!state.activeWorkspaceNode || !state.workspaceSocket || state.workspaceIsApplyingRemote) return;
                if (workspaceEditor.disabled) return;
                const node = state.workspaceNodes.get(state.activeWorkspaceNode);
                if (!node || node.node_type !== 'file') return;
                
                const newContent = workspaceEditor.value;
                const oldContent = state.workspaceContent;
                const cursorPos = workspaceEditor.selectionStart;
                
                // Calculate delta (incremental change)
                const delta = calculateDelta(oldContent, newContent, cursorPos);
                
                if (delta) {
                    // Send incremental update
                    state.workspaceSocket.send(JSON.stringify({
                        type: 'write_file',
                        node_id: state.activeWorkspaceNode,
                        delta: delta,
                        cursor_position: cursorPos
                    }));
                }
                
                // Update local state
                state.workspaceContent = newContent;
                state.workspaceLastContent = newContent;
                
                // Update cursor position (throttled)
                if (state.workspaceCursorUpdateTimer) {
                    clearTimeout(state.workspaceCursorUpdateTimer);
                }
                state.workspaceCursorUpdateTimer = setTimeout(() => {
                    sendCursorUpdate();
                }, 100);
            });
            
            // Track cursor movements
            workspaceEditor.addEventListener('keyup', () => {
                sendCursorUpdate();
            });
            
            workspaceEditor.addEventListener('click', () => {
                sendCursorUpdate();
            });
            
            workspaceEditor.addEventListener('keydown', () => {
                sendCursorUpdate();
            });
        }
        
        function sendCursorUpdate() {
            if (!state.activeWorkspaceNode || !state.workspaceSocket || state.workspaceIsApplyingRemote) return;
            const { workspaceEditor } = state.workspaceUI || {};
            if (!workspaceEditor || workspaceEditor.disabled) return;
            
            state.workspaceSocket.send(JSON.stringify({
                type: 'cursor_update',
                node_id: state.activeWorkspaceNode,
                cursor_position: workspaceEditor.selectionStart,
                selection_start: workspaceEditor.selectionStart,
                selection_end: workspaceEditor.selectionEnd
            }));
        }

        if (workspaceRunBtn) {
            workspaceRunBtn.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                if (!state.activeWorkspaceNode || !state.workspaceSocket || workspaceRunBtn.disabled) return;
                const node = state.workspaceNodes.get(state.activeWorkspaceNode);
                if (!node || node.node_type !== 'file') return;
                const { workspaceEditor } = state.workspaceUI || {};
                if (!workspaceEditor) return;
                
                const code = workspaceEditor.value;
                const language = node.language || 'python';
                
                // Execute code via workspace socket
                state.workspaceSocket.send(JSON.stringify({
                    type: 'execute_code',
                    node_id: state.activeWorkspaceNode,
                    code: code,
                    language: language
                }));
            });
        }

        if (workspaceDownloadBtn) {
            workspaceDownloadBtn.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                if (!state.activeWorkspaceNode || workspaceDownloadBtn.disabled) return;
                const node = state.workspaceNodes.get(state.activeWorkspaceNode);
                if (!node || node.node_type !== 'file') return;
                const { workspaceEditor } = state.workspaceUI || {};
                const content = workspaceEditor ? workspaceEditor.value : (node.content || '');
                const blob = new Blob([content], { type: 'text/plain' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = node.name;
                document.body.appendChild(a);
                a.click();
                a.remove();
                URL.revokeObjectURL(url);
            });
        }
    }

    function handleWorkspaceEvent(payload) {
        const { workspaceEditor, workspaceActive, workspaceLangBadge } = state.workspaceUI || {};

        switch (payload.event) {
            case 'tree_refresh':
                // Rebuild tree from nodes
                state.workspaceNodes = new Map();
                payload.nodes.forEach(node => state.workspaceNodes.set(node.id, node));
                state.workspaceTree = buildWorkspaceTree(Array.from(state.workspaceNodes.values()));
                renderWorkspaceTree();
                
                // If there's an active_id, select it
                if (payload.active_id) {
                    setActiveWorkspaceNode(payload.active_id);
                }
                break;
            case 'run_result':
                updateRunOutput(payload);
                break;
        }
    }

    function setActiveWorkspaceNode(nodeId) {
        const node = state.workspaceNodes.get(nodeId);
        if (!node || !state.workspaceUI) return;
        if (node.node_type !== 'file') return;

        const {
            workspaceEditor,
            workspaceActive,
            workspaceLangBadge,
            workspaceRunBtn,
            workspaceDownloadBtn,
            workspaceRenameBtn,
            workspaceDeleteBtn
        } = state.workspaceUI;

        state.activeWorkspaceNode = nodeId;

        if (workspaceEditor) {
            state.workspaceIsApplyingRemote = true;
            workspaceEditor.disabled = false;
            workspaceEditor.removeAttribute('disabled');
            workspaceEditor.value = node.content || '';
            state.workspaceContent = node.content || '';
            state.workspaceLastContent = node.content || '';
            state.workspaceIsApplyingRemote = false;
            // Focus the editor after a short delay to ensure it's enabled
            setTimeout(() => {
                workspaceEditor.focus();
            }, 50);
        }
        if (workspaceActive) workspaceActive.textContent = node.full_path || node.name;
        if (workspaceLangBadge) {
            workspaceLangBadge.textContent = (node.language || 'text').toUpperCase();
            workspaceLangBadge.classList.remove('d-none');
        }
        [workspaceRunBtn, workspaceDownloadBtn, workspaceRenameBtn, workspaceDeleteBtn].forEach(btn => {
            if (btn) btn.disabled = false;
        });

        // Request file content from server
        if (state.workspaceSocket) {
            state.workspaceSocket.send(JSON.stringify({
                type: 'read_file',
                node_id: nodeId
            }));
            
            // Notify others that we're viewing this file
            state.workspaceSocket.send(JSON.stringify({
                type: 'file_focus',
                node_id: nodeId
            }));
        }

        renderWorkspaceTree();
        renderUserPresence();
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

        state.activeWorkspaceNode = null;
        if (workspaceEditor) {
            workspaceEditor.setAttribute('disabled', 'disabled');
            workspaceEditor.value = '';
            state.workspaceContent = '';
            state.workspaceLastContent = '';
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

    // Collaborative editing functions
    function calculateDelta(oldContent, newContent, cursorPos) {
        // Simple delta calculation - find the change
        if (oldContent === newContent) return null;
        
        // Find the first difference
        let start = 0;
        while (start < oldContent.length && start < newContent.length && 
               oldContent[start] === newContent[start]) {
            start++;
        }
        
        // Find the last difference from the end
        let oldEnd = oldContent.length;
        let newEnd = newContent.length;
        while (oldEnd > start && newEnd > start && 
               oldContent[oldEnd - 1] === newContent[newEnd - 1]) {
            oldEnd--;
            newEnd--;
        }
        
        const deletedLength = oldEnd - start;
        const insertedText = newContent.substring(start, newEnd);
        
        if (deletedLength === 0 && insertedText.length === 0) return null;
        
        return {
            type: deletedLength > 0 ? (insertedText.length > 0 ? 'replace' : 'delete') : 'insert',
            position: start,
            text: insertedText,
            length: deletedLength
        };
    }
    
    function applyDelta(content, delta) {
        if (!delta) return content;
        
        const { type, position, text, length } = delta;
        
        if (type === 'insert' || type === 'replace') {
            const before = content.substring(0, position);
            const after = type === 'replace' 
                ? content.substring(position + length)
                : content.substring(position);
            return before + text + after;
        } else if (type === 'delete') {
            return content.substring(0, position) + content.substring(position + length);
        }
        
        return content;
    }
    
    function handleFileUpdate(data) {
        const { workspaceEditor } = state.workspaceUI || {};
        if (!workspaceEditor || data.node_id !== state.activeWorkspaceNode) return;
        
        // Don't apply our own updates (check if we have currentUserId set)
        const currentUserId = window.currentUserId || null;
        if (currentUserId && data.user_id === currentUserId) return;
        
        state.workspaceIsApplyingRemote = true;
        const cursorPos = workspaceEditor.selectionStart;
        const scrollTop = workspaceEditor.scrollTop;
        
        if (data.delta) {
            // Apply incremental delta
            state.workspaceContent = applyDelta(state.workspaceContent, data.delta);
            workspaceEditor.value = state.workspaceContent;
            state.workspaceLastContent = state.workspaceContent;
        } else if (data.content !== undefined) {
            // Fallback to full content update
            workspaceEditor.value = data.content;
            state.workspaceContent = data.content;
            state.workspaceLastContent = data.content;
        }
        
        // Restore cursor position
        workspaceEditor.setSelectionRange(cursorPos, cursorPos);
        workspaceEditor.scrollTop = scrollTop;
        state.workspaceIsApplyingRemote = false;
        
        // Show notification
        if (data.display_name || data.username) {
            showEditNotification(data.display_name || data.username, data.user_color || '#4ECDC4');
        }
    }
    
    function handleCursorUpdate(data) {
        if (data.node_id !== state.activeWorkspaceNode) return;
        const currentUserId = window.currentUserId || null;
        if (currentUserId && data.user_id === currentUserId) return;
        
        // Store cursor info
        state.workspaceCursors.set(data.user_id, {
            position: data.cursor_position,
            selectionStart: data.selection_start,
            selectionEnd: data.selection_end,
            username: data.display_name || data.username,
            color: data.user_color
        });
        
        renderUserPresence();
    }
    
    function handleFileFocus(data) {
        const currentUserId = window.currentUserId || null;
        if (currentUserId && data.user_id === currentUserId) return;
        
        // Update user's active file
        if (!state.workspaceUsers.has(data.user_id)) {
            state.workspaceUsers.set(data.user_id, {
                username: data.username,
                display_name: data.display_name,
                color: data.user_color,
                active_file: data.node_id
            });
        } else {
            const user = state.workspaceUsers.get(data.user_id);
            user.active_file = data.node_id;
        }
        
        renderUserPresence();
    }
    
    function handleUserJoined(data) {
        state.workspaceUsers.set(data.user_id, {
            username: data.username,
            display_name: data.display_name,
            color: data.user_color,
            active_file: null
        });
        renderUserPresence();
    }
    
    function handleUserLeft(data) {
        state.workspaceUsers.delete(data.user_id);
        state.workspaceCursors.delete(data.user_id);
        renderUserPresence();
    }
    
    function renderUserPresence() {
        // Create or update user presence indicator
        let presenceContainer = document.getElementById('workspace-user-presence');
        if (!presenceContainer && state.workspaceUI?.workspaceActive) {
            presenceContainer = document.createElement('div');
            presenceContainer.id = 'workspace-user-presence';
            presenceContainer.className = 'workspace-user-presence';
            presenceContainer.style.cssText = 'display: flex; gap: 8px; align-items: center; padding: 4px 8px; background: rgba(0,0,0,0.3); border-radius: 4px; margin-top: 4px; flex-wrap: wrap;';
            state.workspaceUI.workspaceActive.parentElement.appendChild(presenceContainer);
        }
        
        if (!presenceContainer) return;
        
        // Clear and rebuild
        presenceContainer.innerHTML = '';
        
        const activeUsers = Array.from(state.workspaceUsers.values()).filter(
            user => user.active_file === state.activeWorkspaceNode
        );
        
        if (activeUsers.length === 0) {
            presenceContainer.style.display = 'none';
            return;
        }
        
        presenceContainer.style.display = 'flex';
        activeUsers.forEach(user => {
            const badge = document.createElement('span');
            badge.className = 'user-presence-badge';
            badge.style.cssText = `display: inline-flex; align-items: center; gap: 4px; padding: 2px 6px; background: ${user.color}20; border: 1px solid ${user.color}; border-radius: 12px; font-size: 11px; color: ${user.color};`;
            badge.innerHTML = `<span style="width: 6px; height: 6px; background: ${user.color}; border-radius: 50%; display: inline-block;"></span> ${user.display_name || user.username}`;
            presenceContainer.appendChild(badge);
        });
    }
    
    function showEditNotification(username, color) {
        // Show a subtle notification that someone edited
        const notification = document.createElement('div');
        notification.className = 'edit-notification';
        notification.style.cssText = `position: fixed; top: 20px; right: 20px; padding: 8px 12px; background: ${color}20; border-left: 3px solid ${color}; border-radius: 4px; color: ${color}; font-size: 12px; z-index: 10000; animation: slideIn 0.3s ease;`;
        notification.textContent = `${username} is editing...`;
        document.body.appendChild(notification);
        
        setTimeout(() => {
            notification.style.animation = 'slideOut 0.3s ease';
            setTimeout(() => notification.remove(), 300);
        }, 2000);
    }
    
    // Add CSS animations if not present
    if (!document.getElementById('workspace-collab-styles')) {
        const style = document.createElement('style');
        style.id = 'workspace-collab-styles';
        style.textContent = `
            @keyframes slideIn {
                from { transform: translateX(100%); opacity: 0; }
                to { transform: translateX(0); opacity: 1; }
            }
            @keyframes slideOut {
                from { transform: translateX(0); opacity: 1; }
                to { transform: translateX(100%); opacity: 0; }
            }
        `;
        document.head.appendChild(style);
    }

    function getCsrfToken() {
        const match = document.cookie.match(/csrftoken=([^;]+)/);
        return match ? match[1] : '';
    }
})();

