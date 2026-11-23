import type { ViewerTheme } from "./types";

export const plain: ViewerTheme = {
  id: "plain",
  name: "Plain",
  Choice: ({ label, value, options, onChange, disabled }) => (
    <label className="field">
      <span className="field-label">{label}</span>
      <select value={value} onChange={event => onChange(event.target.value)} disabled={disabled}>
        {options.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
      </select>
    </label>
  ),
  Button: ({ children, onClick }) => <button type="button" onClick={onClick}>{children}</button>,
  Frame: () => null,
  Icon: () => null,
};
