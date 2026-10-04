import { useId, useState } from "react";
import type { KeepPadding } from "../api/types";
import styles from "./PaddingSettings.module.css";
import type { PaddingControl, PaddingSaveStatus } from "./usePadding";

// backend が受け付ける範囲（Design Doc 3-5）
const MIN_PAD_MS = 0;
const MAX_PAD_MS = 2000;
const STEP_MS = 50;
const INVALID_NOTE = `${MIN_PAD_MS}〜${MAX_PAD_MS} の整数で入力してください`;
const WHOLE_NUMBER = /^\d+$/;

const FIELDS: readonly { key: keyof KeepPadding; label: string }[] = [
  { key: "before_ms", label: "前" },
  { key: "after_ms", label: "後ろ" },
  { key: "after_sentence_ms", label: "文の終わりのあと" },
];

const STATUS_LABELS: Readonly<
  Record<Exclude<PaddingSaveStatus["name"], "failed">, string>
> = {
  saved: "保存済み",
  dirty: "未保存",
  saving: "保存中…",
};

/**
 * 間の設定（Design Doc 3-6）: 無音を削るときに、残す発話の前・後ろ・文の終わりのあとに残す間。
 * 値を変えると、すぐにプレビューに効き、少し遅れて保存する。ワークスペース全体で 1 組（どのレクチャーにも効く）。
 */
export function PaddingSettings({ control }: { control: PaddingControl }) {
  const { padding, status, defaults } = control;
  const titleId = useId();
  // 使えない値を入力している項目。その間は、プレビューにも保存にも使わない
  const [invalid, setInvalid] = useState<ReadonlySet<keyof KeepPadding>>(
    new Set(),
  );
  const mark = (key: keyof KeepPadding, isInvalid: boolean) => {
    const next = new Set(invalid);
    if (isInvalid) {
      next.add(key);
    } else {
      next.delete(key);
    }
    setInvalid(next);
  };

  return (
    <details className={styles.settings}>
      <summary id={titleId}>間の設定</summary>
      {/* biome-ignore lint/a11y/useSemanticElements: fieldset は、details の中で見出し（summary）と名前を共有できない */}
      <div role="group" aria-labelledby={titleId} className={styles.body}>
        <p className={styles.note}>
          無音を削るときに残す間（ミリ秒）。もとの無音より長くはなりません。
          すべてのレクチャーの、プレビューと書き出しに効きます。
          {defaults !== null &&
            `既定は ${defaults.before_ms}・${defaults.after_ms}・${defaults.after_sentence_ms}。`}
        </p>
        <div className={styles.fields}>
          {FIELDS.map(({ key, label }) => (
            <PadField
              key={key}
              label={label}
              value={padding[key]}
              onChange={(value) => control.change({ ...padding, [key]: value })}
              onValidity={(isInvalid) => mark(key, isInvalid)}
            />
          ))}
          <button
            type="button"
            className={styles.reset}
            onClick={() => {
              setInvalid(new Set());
              control.reset();
            }}
          >
            既定に戻す
          </button>
          {status.name !== "failed" && (
            <span
              role="status"
              data-testid="padding-status"
              className={styles.status}
            >
              {STATUS_LABELS[status.name]}
            </span>
          )}
        </div>
        {invalid.size > 0 && (
          <p role="alert" className={styles.failure}>
            {INVALID_NOTE}
          </p>
        )}
        {status.name === "failed" && (
          <p role="alert" className={styles.failure}>
            間の設定を保存できませんでした: {status.message}
          </p>
        )}
      </div>
    </details>
  );
}

/** 0〜2000 の整数として読めれば、その数。読めなければ null。 */
function parsePad(text: string): number | null {
  if (!WHOLE_NUMBER.test(text)) {
    return null;
  }
  const value = Number(text);
  return value >= MIN_PAD_MS && value <= MAX_PAD_MS ? value : null;
}

function PadField({
  label,
  value,
  onChange,
  onValidity,
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
  onValidity: (invalid: boolean) => void;
}) {
  // 入力の途中の文字。使える値になったら null に戻し、渡された値（value）をそのまま出す
  const [draft, setDraft] = useState<string | null>(null);
  return (
    <label className={styles.field}>
      {label}
      <input
        type="number"
        className={styles.input}
        min={MIN_PAD_MS}
        max={MAX_PAD_MS}
        step={STEP_MS}
        value={draft ?? String(value)}
        aria-invalid={draft !== null}
        onChange={(event) => {
          const parsed = parsePad(event.target.value);
          setDraft(parsed === null ? event.target.value : null);
          onValidity(parsed === null);
          if (parsed !== null && parsed !== value) {
            onChange(parsed);
          }
        }}
        onBlur={() => {
          // 使えない値のまま離れたら、使っている値に戻す
          if (draft !== null) {
            setDraft(null);
            onValidity(false);
          }
        }}
      />
    </label>
  );
}
