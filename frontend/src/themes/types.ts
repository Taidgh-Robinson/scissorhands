import type { ComponentType, ReactNode } from "react";

export interface ChoiceProps {
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (value: string) => void;
  disabled?: boolean;
}

export interface ViewerTheme {
  id: string;
  name: string;
  colorScheme?: "light" | "dark";
  rootClass?: string;
  illustration?: string;
  Choice: ComponentType<ChoiceProps>;
  Button: ComponentType<{ children: ReactNode; onClick: () => void }>;
  Frame: ComponentType;
  Icon: ComponentType<{ name: "folder-open" | "file-text" | "layers" | "palette"; size?: number }>;
}
