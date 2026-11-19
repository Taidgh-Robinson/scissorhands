import { SketchButton, SketchIcon, SketchOutline, SketchSelect } from "blackchalk/static";
import type { ViewerTheme } from "./types";

export const blackchalk: ViewerTheme = {
  id: "blackchalk",
  name: "BlackChalk",
  colorScheme: "light",
  rootClass: "sketch-paper",
  illustration: new URL("./scissors.webp", import.meta.url).href,
  Choice: ({ label, value, options, onChange, disabled }) => (
    <div className="field">
      <span className="field-label">{label}</span>
      <SketchSelect
        aria-label={label}
        selected={value}
        options={options}
        onChange={onChange}
        disabled={disabled}
      />
    </div>
  ),
  Button: ({ children, onClick }) => (
    <SketchButton variant="secondary" onClick={onClick}>{children}</SketchButton>
  ),
  Frame: () => <SketchOutline aria-hidden="true" style={{ position: "absolute", inset: 0, pointerEvents: "none" }} />,
  Icon: SketchIcon,
};

export const blackchalkDark: ViewerTheme = {
  ...blackchalk,
  id: "blackchalk-dark",
  name: "BlackChalk Dark",
  colorScheme: "dark",
};
