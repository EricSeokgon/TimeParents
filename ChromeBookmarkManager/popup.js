document.addEventListener('DOMContentLoaded', () => {
    updateStats();

    document.getElementById('open-manager').addEventListener('click', () => {
        chrome.tabs.create({ url: 'manager.html' });
    });
});

function updateStats() {
    chrome.bookmarks.getTree((bookmarkTreeNodes) => {
        let totalBookmarks = 0;
        let totalFolders = 0;

        function countNodes(nodes) {
            for (const node of nodes) {
                if (node.url) {
                    totalBookmarks++;
                } else {
                    totalFolders++;
                    if (node.children) {
                        countNodes(node.children);
                    }
                }
            }
        }

        countNodes(bookmarkTreeNodes);
        // Subtract root folders (usually 2: Bookmarks Bar, Other Bookmarks)
        totalFolders = Math.max(0, totalFolders - 1);

        document.getElementById('total-bookmarks').textContent = totalBookmarks;
        document.getElementById('total-folders').textContent = totalFolders;
    });
}
