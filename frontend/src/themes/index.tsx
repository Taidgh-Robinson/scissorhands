import { createContext, useContext, useState, type ReactNode } from "react";
import { blackchalk, blackchalkDark } from "./blackchalk";
import { plain } from "./plain";

export const themes = [blackchalk, blackchalkDark, plain];
const preferenceKey = "scissorhands.viewer.theme";

function storedTheme() {
  try {
    const id = window.localStorage.getItem(preferenceKey);
    return themes.find(theme => theme.id === id) ?? blackchalk;
  } catch {
    return blackchalk;
  }
}

const ThemeContext = createContext(blackchalk);
export const useTheme = () => useContext(ThemeContext);

export function Viewer({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState(storedTheme);
  const { Icon } = theme;
  function chooseTheme(id: string) {
    const next = themes.find(entry => entry.id === id);
    if (!next) return;
    setTheme(next);
    try {
      window.localStorage.setItem(preferenceKey, next.id);
    } catch {
      // The in-memory choice still applies when browser storage is unavailable.
    }
  }
  return (
    <ThemeContext.Provider value={theme}>
      <div className={theme.rootClass} data-ui-theme={theme.id} data-theme={theme.colorScheme}>
        <header className="masthead">
          <div className="masthead-inner">
            <span className="wordmark"><span className="brand-symbol" aria-hidden="true">✂︎</span>Scissorhands</span>
            <label className="theme-picker">
              <Icon name="palette" size={18} />
              <span>Theme</span>
              <select value={theme.id} onChange={event => chooseTheme(event.target.value)}>
                {themes.map(entry => <option key={entry.id} value={entry.id}>{entry.name}</option>)}
              </select>
            </label>
          </div>
        </header>
        {children}
      </div>
    </ThemeContext.Provider>
  );
}
