function resolveTheme(theme, entryUrl) {
  if (theme instanceof URL) return theme;
  if (typeof theme !== 'string' || !theme.trim()) throw new Error('WebGUI theme must be a built-in name, path or URL');
  const value = theme.trim();
  if (/^[a-z0-9_-]+$/i.test(value)) return new URL(`./themes/${value}.css`, entryUrl);
  const base = globalThis.document?.baseURI ?? entryUrl;
  return new URL(value, base);
}

function installTheme(document, url) {
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = String(url);
  link.dataset.webguiTheme = '';
  (document.head ?? document.documentElement).append(link);
  return link;
}

export { installTheme, resolveTheme };
