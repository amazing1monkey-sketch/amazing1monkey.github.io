(() => {
  'use strict';
  const data = window.SITE_DATA;
  const params = new URLSearchParams(location.search);
  let language = params.get('lang');
  if (!['zh', 'en'].includes(language)) {
    try { language = localStorage.getItem('sqh-language'); } catch (_) {}
  }
  if (!['zh', 'en'].includes(language)) language = 'zh';
  let activePage = Number(params.get('page') || 0);
  const words = {
    zh: { skip: '跳转到正文', nav: '页面导航', empty: '内容待添加', close: '关闭图片', view: '查看大图', error: '图片暂时无法加载', footer: '个人主页' },
    en: { skip: 'Skip to content', nav: 'Page navigation', empty: 'Content to be added', close: 'Close image', view: 'View full image', error: 'Image unavailable', footer: 'Personal website' }
  };
  const el = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  function address(index, lang = language) {
    return `index.html?lang=${lang}&page=${index}`;
  }
  function pageLabel(page, index) {
    if (!/^(?:sheet|工作表)\s*\d+$/i.test(page.title.trim())) return page.title;
    if (index === 0) return language === 'zh' ? '个人信息' : 'Profile';
    return page.modules[0]?.title || (language === 'zh' ? `内容 ${index + 1}` : `Collection ${index + 1}`);
  }
  function render() {
    if (!data) {
      document.getElementById('app').append(el('main', 'container empty-list', '网站内容未生成，请先运行 python3 scripts/build.py。'));
      return;
    }
    const pages = data.languages[language];
    if (!Number.isInteger(activePage) || activePage < 0 || activePage >= pages.length) activePage = 0;
    const page = pages[activePage];
    const text = words[language];
    const name = data.names[language];
    document.documentElement.lang = language === 'zh' ? 'zh-CN' : 'en';
    document.title = `${name} | ${pageLabel(page, activePage)}`;
    document.querySelector('meta[name="description"]').content = `${name} · ${page.modules.map(module => module.title).join(' · ')}`;
    const root = document.getElementById('app');
    root.replaceChildren();
    const skip = el('a', 'skip-link', text.skip); skip.href = '#main'; root.append(skip);
    const header = el('header', 'site-header');
    const inner = el('div', 'container header-inner');
    const brand = el('a', 'brand'); brand.href = address(0);
    const mark = el('span', 'brand-mark', data.names.zh.slice(0, 1)); mark.setAttribute('aria-hidden', 'true');
    brand.append(mark, el('span', 'brand-name', name)); inner.append(brand);
    const controls = el('div', 'header-controls');
    const nav = el('nav'); nav.setAttribute('aria-label', text.nav);
    pages.forEach((entry, index) => {
      const link = el('a', '', pageLabel(entry, index)); link.href = address(index);
      if (index === activePage) link.setAttribute('aria-current', 'page');
      nav.append(link);
    });
    if (pages.length > 1) controls.append(nav);
    else inner.classList.add('single-page-header');
    const languages = el('div', 'languages'); languages.setAttribute('role', 'group'); languages.setAttribute('aria-label', 'Language / 语言');
    [['zh', '中'], ['en', 'EN']].forEach(([key, label], index) => {
      if (index) languages.append(el('span', 'language-divider', '/'));
      const button = el('button', '', label); button.type = 'button'; button.lang = key;
      button.setAttribute('aria-label', key === 'zh' ? '切换为中文' : 'Switch to English');
      button.setAttribute('aria-pressed', String(key === language));
      button.onclick = () => {
        language = key;
        if (!data.languages[language][activePage]) activePage = 0;
        try { localStorage.setItem('sqh-language', language); } catch (_) {}
        try { history.replaceState(null, '', address(activePage)); } catch (_) {}
        render();
        document.querySelector(`.languages button[lang="${key}"]`).focus();
      };
      languages.append(button);
    });
    controls.append(languages); inner.append(controls); header.append(inner); root.append(header);
    const main = el('main', 'container workbook-main'); main.id = 'main'; main.tabIndex = -1;
    const pageHeading = el('div', 'page-label-row');
    pageHeading.append(el('p', 'page-label', pageLabel(page, activePage)));
    const pageNumber = el('span', 'page-index', String(activePage + 1).padStart(2, '0'));
    pageNumber.setAttribute('aria-label', language === 'zh' ? `第 ${activePage + 1} 页` : `Page ${activePage + 1}`);
    pageHeading.append(pageNumber); main.append(pageHeading);
    const modules = el('div', 'workbook-modules');
    page.modules.forEach((module, index) => {
      const hasImages = module.items.some(item => item.type === 'image');
      const introduction = activePage === 0 && index === 0 && module.items.some(item => item.type === 'text');
      const firstText = introduction ? module.items.find(item => item.type === 'text') : null;
      const section = el('section', `workbook-module${hasImages ? ' module-with-images' : ''}${introduction ? ' introduction-module' : ''}`);
      const title = el('div', 'module-title');
      const number = el('span', 'row-number', String(index + 1).padStart(2, '0'));
      number.setAttribute('aria-hidden', 'true'); title.append(number);
      if (introduction) title.append(el('p', 'eyebrow', module.title));
      else title.append(el(index === 0 ? 'h1' : 'h2', '', module.title));
      section.append(title);
      const content = el('div', `module-content${hasImages ? ' has-images' : ''}`);
      let run = null;
      for (const item of module.items) {
        if (item.type === 'image') {
          run = null;
          const figure = el('figure', 'image-block');
          const button = el('button', 'workbook-image'); button.type = 'button'; button.setAttribute('aria-label', `${text.view}: ${module.title}`);
          const img = el('img'); img.src = item.src; img.alt = module.title; img.loading = 'lazy'; img.decoding = 'async';
          img.addEventListener('error', () => { button.disabled = true; img.replaceWith(el('span', 'image-error', text.error)); });
          button.append(img); button.onclick = () => openImage(item, module.title, text);
          figure.append(button); content.append(figure);
        } else {
          if (!run) { run = el('div', 'text-run'); content.append(run); }
          if (item === firstText) {
            const firstLine = item.text.split('\n')[0];
            const headline = firstLine.split(/[（(]/)[0].trim();
            run.append(el('h1', 'introduction-name', headline));
            const details = firstLine.slice(headline.length).replace(/^[（(]|[）)]$/g, '').trim();
            if (details) run.append(el('p', 'name-detail', details));
            const remainder = item.text.split('\n').slice(1).join('\n');
            if (remainder) run.append(el('p', 'cell-text', remainder));
          } else run.append(el('p', 'cell-text', item.text));
        }
      }
      if (!module.items.length) content.append(el('p', 'pending', text.empty));
      section.append(content); modules.append(section);
    });
    if (!page.modules.length) modules.append(el('p', 'empty-list', text.empty));
    main.append(modules); root.append(main);
    const footer = el('footer', 'site-footer'); const footerInner = el('div', 'container footer-inner');
    footerInner.append(el('span', '', `© ${new Date().getFullYear()} ${name}`), el('span', '', text.footer));
    footer.append(footerInner); root.append(footer);
  }
  function openImage(item, title, text) {
    const dialog = el('dialog'); dialog.setAttribute('aria-label', title);
    const close = el('button', 'dialog-close', '×'); close.type = 'button'; close.setAttribute('aria-label', text.close); close.onclick = () => dialog.close();
    const img = el('img', 'lightbox-image'); img.src = item.src; img.alt = title;
    dialog.append(close, img); document.body.append(dialog);
    dialog.addEventListener('close', () => dialog.remove());
    dialog.addEventListener('click', event => {
      if (event.target !== dialog) return;
      const rect = dialog.getBoundingClientRect();
      if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.close();
    });
    dialog.showModal();
  }
  window.addEventListener('popstate', () => {
    const query = new URLSearchParams(location.search);
    language = query.get('lang') === 'en' ? 'en' : 'zh';
    activePage = Number(query.get('page') || 0); render();
  });
  render();
})();
