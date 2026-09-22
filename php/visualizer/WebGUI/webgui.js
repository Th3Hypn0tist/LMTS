// Public WebGUI entry point. This is the only JavaScript entry in the repository root.
import { DOMStructure } from './core/dom-structure.js';
import { installTheme, resolveTheme } from './core/theme.js';

const WEBGUI_VERSION = '0.1.0';

class WebGUI extends DOMStructure {
  constructor({ document = globalThis.document, theme = 'default' } = {}) {
    super({ document });
    this.theme = theme;
    this.themeLink = theme == null ? null : installTheme(this.document, resolveTheme(theme, import.meta.url));
  }

  setTheme(theme) {
    const next = theme == null ? null : installTheme(this.document, resolveTheme(theme, import.meta.url));
    this.themeLink?.remove();
    this.theme = theme;
    this.themeLink = next;
    return this;
  }

  destroy() {
    super.destroy();
    this.themeLink?.remove();
    this.themeLink = null;
  }
}

const createWebGUI = options => new WebGUI(options);

export { WEBGUI_VERSION, WebGUI, createWebGUI, resolveTheme };
