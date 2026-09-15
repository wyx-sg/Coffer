// frontend/src/components/reach/ReachChoice.tsx
// One radio row of ReachControl's panel. Split out so the control itself
// stays within its size budget; it owns no state.
//
// `onClick`, not `onChange`: re-picking the live choice is a real gesture (it
// is how a user confirms and closes) and an already-checked radio fires no
// change. Keyboard activation clicks too, so nothing is lost; `readOnly` only
// tells React the missing `onChange` is meant.
interface Props {
  /** Radio group name — per ReachControl instance, never shared. */
  group: string;
  checked: boolean;
  disabled: boolean;
  text: string;
  onPick: () => void;
}

export function ReachChoice({ group, checked, disabled, text, onPick }: Props) {
  return (
    <label className="flex w-full cursor-pointer items-center gap-2 text-sm">
      <input
        type="radio"
        name={group}
        className="size-4 cursor-pointer accent-primary align-middle"
        checked={checked}
        disabled={disabled}
        readOnly
        onClick={onPick}
      />
      <span>{text}</span>
    </label>
  );
}
