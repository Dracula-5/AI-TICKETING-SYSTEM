import { TextField, type TextFieldProps } from "@mui/material";

// Mirrors backend/app/schemas/auth.py::_check_password.
export function passwordProblem(value: string): string | null {
  if (!value) return null;
  if (value.length < 10) return "At least 10 characters";
  if (new TextEncoder().encode(value).length > 72) return "At most 72 bytes";
  if (value.toLowerCase() === value || value.toUpperCase() === value || !/\d/.test(value))
    return "Mix upper- and lower-case letters and include a digit";
  return null;
}

export function NewPasswordField(props: TextFieldProps & { value: string }) {
  const problem = passwordProblem(props.value);
  return (
    <TextField
      type="password"
      autoComplete="new-password"
      error={!!problem}
      helperText={problem ?? "10+ characters with upper- and lower-case letters and a digit"}
      {...props}
    />
  );
}
