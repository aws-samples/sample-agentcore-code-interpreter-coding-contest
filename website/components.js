// Favicon
if (!document.querySelector('link[rel="icon"]')) {
    const link = document.createElement('link');
    link.rel = 'icon';
    link.href = "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>⚡</text></svg>";
    document.head.appendChild(link);
}

// ヘッダーコンポーネント
class AppHeader extends HTMLElement {
    connectedCallback() {
        this.innerHTML = `
            <div class="header">
                <h1>Prompt Jam</h1>
                <p>最速で問題を解こう！</p>
            </div>
        `;
    }
}

// ナビゲーションコンポーネント
class AppNav extends HTMLElement {
    connectedCallback() {
        const current = this.getAttribute('current') || '';
        this.innerHTML = `
            <div class="nav">
                <a href="index.html" class="${current === 'home' ? 'active' : ''}">リーダーボード</a>
                <a href="problems.html" class="${current === 'problems' ? 'active' : ''}">問題</a>
                <a href="admin.html" class="${current === 'admin' ? 'active' : ''}">管理</a>
            </div>
        `;
    }
}

customElements.define('app-header', AppHeader);
customElements.define('app-nav', AppNav);