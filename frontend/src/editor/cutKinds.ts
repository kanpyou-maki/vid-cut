import type { CutKind } from "../api/types";

/** 削除の種類（自動の削除候補の種類と、手動）と、画面に出す名前。 */
export type Kind = CutKind | "manual";

export const KIND_LABELS: Readonly<Record<Kind, string>> = {
  retake: "言い直し",
  misspeak: "言い間違い",
  noise: "雑音",
  filler: "フィラー",
  silence: "無音",
  manual: "手動",
};

/** 自動の削除候補を戻した（削除しないと決めた）状態の名前。 */
export const RESTORED_LABEL = "戻し済み";
