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
                <a href="index.html" class="${current === 'home' ? 'active' : ''}">ホーム</a>
                <a href="problems.html" class="${current === 'problems' ? 'active' : ''}">問題一覧</a>
                <a href="admin.html" class="${current === 'admin' ? 'active' : ''}">管理</a>
            </div>
        `;
    }
}

customElements.define('app-header', AppHeader);
customElements.define('app-nav', AppNav);