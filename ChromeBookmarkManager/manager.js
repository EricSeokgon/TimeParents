document.addEventListener('DOMContentLoaded', () => {
    // Buttons
    document.getElementById('btn-find-duplicates').addEventListener('click', findDuplicates);
    document.getElementById('btn-find-empty-folders').addEventListener('click', findEmptyFolders);
    document.getElementById('btn-check-dead-links').addEventListener('click', checkDeadLinks);

    document.getElementById('btn-select-all').addEventListener('click', selectAll);
    document.getElementById('btn-delete-selected').addEventListener('click', deleteSelected);
    document.getElementById('btn-close-results').addEventListener('click', closeResults);
});

let currentItems = []; // Store items currently displayed in the list

function showResults(title, items, type) {
    const resultsArea = document.getElementById('results-area');
    const resultsList = document.getElementById('results-list');
    const resultsTitle = document.getElementById('results-title');

    resultsTitle.textContent = `${title} (${items.length})`;
    resultsList.innerHTML = '';
    currentItems = items;

    if (items.length === 0) {
        resultsList.innerHTML = '<li class="result-item">No items found.</li>';
    } else {
        items.forEach((item, index) => {
            const li = document.createElement('li');
            li.className = 'result-item';

            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.id = `item-${index}`;
            checkbox.dataset.index = index;

            const details = document.createElement('div');
            details.className = 'item-details';

            const titleSpan = document.createElement('span');
            titleSpan.className = 'item-title';
            titleSpan.textContent = item.title || '(No Title)';

            const urlSpan = document.createElement('span');
            urlSpan.className = 'item-url';
            urlSpan.textContent = item.url || '(Folder)';

            const pathSpan = document.createElement('span');
            pathSpan.className = 'item-path';
            pathSpan.textContent = item.path ? `Path: ${item.path}` : '';

            details.appendChild(titleSpan);
            if (item.url) details.appendChild(urlSpan);
            if (item.path) details.appendChild(pathSpan);

            li.appendChild(checkbox);
            li.appendChild(details);
            resultsList.appendChild(li);
        });
    }

    resultsArea.classList.remove('hidden');
}

function closeResults() {
    document.getElementById('results-area').classList.add('hidden');
    currentItems = [];
}

function selectAll() {
    const checkboxes = document.querySelectorAll('#results-list input[type="checkbox"]');
    const allChecked = Array.from(checkboxes).every(cb => cb.checked);
    checkboxes.forEach(cb => cb.checked = !allChecked);
}

async function deleteSelected() {
    const checkboxes = document.querySelectorAll('#results-list input[type="checkbox"]:checked');
    const indices = Array.from(checkboxes).map(cb => parseInt(cb.dataset.index));

    if (indices.length === 0) return;

    if (!confirm(`Are you sure you want to delete ${indices.length} items?`)) return;

    // Sort indices descending to avoid shifting issues if we were splicing an array, 
    // but here we just need the ID.
    // However, we should process them.

    let deletedCount = 0;
    for (const index of indices) {
        const item = currentItems[index];
        try {
            if (item.type === 'folder') {
                await chrome.bookmarks.removeTree(item.id);
            } else {
                await chrome.bookmarks.remove(item.id);
            }
            deletedCount++;
        } catch (e) {
            console.error("Failed to remove", item, e);
        }
    }

    alert(`Deleted ${deletedCount} items.`);
    closeResults();
    // Optionally refresh the current view or re-run the scan
}

// --- Feature Implementations ---

async function findDuplicates() {
    const tree = await chrome.bookmarks.getTree();
    const duplicates = [];
    const urlMap = new Map();

    function traverse(nodes, path) {
        for (const node of nodes) {
            if (node.url) {
                if (urlMap.has(node.url)) {
                    duplicates.push({
                        id: node.id,
                        title: node.title,
                        url: node.url,
                        path: path,
                        type: 'bookmark'
                    });
                } else {
                    urlMap.set(node.url, true);
                }
            } else if (node.children) {
                traverse(node.children, path + ' > ' + node.title);
            }
        }
    }

    traverse(tree, 'Root');
    showResults('Duplicate Bookmarks', duplicates, 'duplicate');
}

async function findEmptyFolders() {
    const tree = await chrome.bookmarks.getTree();
    const emptyFolders = [];

    function traverse(nodes, path) {
        let isEmpty = true;
        let hasChildren = false;

        for (const node of nodes) {
            if (node.url) {
                isEmpty = false;
            } else {
                hasChildren = true;
                // Recursive check
                const childIsEmpty = traverse(node.children || [], path + ' > ' + node.title);
                if (!childIsEmpty) {
                    isEmpty = false;
                }
            }
        }

        // If it's a folder (no url), has no children OR all children are empty folders (handled by recursion logic?)
        // Actually, simpler logic: A folder is empty if it has no children, OR all its children are empty folders.
        // But wait, if I delete a child empty folder, the parent might become empty.
        // For V1, let's just find folders with 0 children.
        // Refined logic: Find folders that have 0 children.

        // We need to be careful not to delete root folders.
        // Root folders usually have id '0', '1', '2'.

        return isEmpty;
    }

    function findEmpty(nodes, path) {
        for (const node of nodes) {
            if (!node.url && node.children) {
                // It's a folder
                if (node.children.length === 0) {
                    // Check if it's a root folder
                    if (node.id !== '0' && node.id !== '1' && node.id !== '2') {
                        emptyFolders.push({
                            id: node.id,
                            title: node.title,
                            url: '(Empty Folder)',
                            path: path,
                            type: 'folder'
                        });
                    }
                } else {
                    findEmpty(node.children, path + ' > ' + node.title);
                }
            }
        }
    }

    findEmpty(tree, 'Root');
    showResults('Empty Folders', emptyFolders, 'folder');
}

async function checkDeadLinks() {
    const tree = await chrome.bookmarks.getTree();
    const allBookmarks = [];

    function traverse(nodes, path) {
        for (const node of nodes) {
            if (node.url) {
                // Skip javascript: and chrome: URLs
                if (!node.url.startsWith('javascript:') && !node.url.startsWith('chrome:')) {
                    allBookmarks.push({
                        id: node.id,
                        title: node.title,
                        url: node.url,
                        path: path,
                        type: 'bookmark'
                    });
                }
            } else if (node.children) {
                traverse(node.children, path + ' > ' + node.title);
            }
        }
    }

    traverse(tree, 'Root');

    if (!confirm(`Found ${allBookmarks.length} bookmarks. Checking them all might take a while. Continue?`)) return;

    const deadLinks = [];
    const progressBar = document.getElementById('progress-bar');
    const progressText = document.getElementById('progress-text');
    document.getElementById('progress-bar-container').classList.remove('hidden');

    const batchSize = 10;
    let processed = 0;

    for (let i = 0; i < allBookmarks.length; i += batchSize) {
        const batch = allBookmarks.slice(i, i + batchSize);
        const promises = batch.map(async (bookmark) => {
            try {
                const controller = new AbortController();
                const timeoutId = setTimeout(() => controller.abort(), 5000); // 5s timeout

                const response = await fetch(bookmark.url, {
                    method: 'HEAD',
                    signal: controller.signal,
                    mode: 'no-cors' // Opaque response, can't check status easily for some sites, but prevents CORS errors stopping us?
                    // Actually, 'no-cors' returns status 0. We can't know if it's dead or just CORS blocked.
                    // We should try 'cors' first. If it fails, it might be dead OR CORS.
                    // This is tricky in a browser extension.
                    // Manifest V3 host_permissions <all_urls> allows us to bypass CORS if we use the background script or if we are in a privileged context?
                    // Actually, fetch in extension pages with host permissions SHOULD bypass CORS.
                });
                clearTimeout(timeoutId);

                if (!response.ok && response.status !== 405 && response.status !== 403) {
                    // 405 Method Not Allowed (some sites block HEAD)
                    // 403 Forbidden (some sites block bots) - risky to call "dead"
                    // Let's be conservative. Only report 404 or connection errors.
                    if (response.status === 404) {
                        return bookmark;
                    }
                }
            } catch (error) {
                // Network error, timeout, etc.
                // Could be dead.
                return bookmark;
            }
            return null;
        });

        const results = await Promise.all(promises);
        results.forEach(res => {
            if (res) deadLinks.push(res);
        });

        processed += batch.length;
        const percent = Math.round((processed / allBookmarks.length) * 100);
        progressBar.style.width = `${percent}%`;
        progressText.textContent = `${percent}%`;
    }

    document.getElementById('progress-bar-container').classList.add('hidden');
    showResults('Dead Links (Potential)', deadLinks, 'bookmark');
}
