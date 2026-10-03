/**
 * 文字起こしの要素に付ける data 属性の名前。文字起こしを描く部品（TranscriptView）と、
 * その要素を探す部品（CutReason・useReviewNavigation）の間の取り決め。
 */

/** 判定の理由を出す対象（自動の削除候補。削除済み・戻し済み）の id。CutReason が読む。 */
export const SUGGESTION_ID_ATTRIBUTE = "data-suggestion-id";
/** 段落のチャンクの id（言い直し先への移動に使う） */
export const CHUNK_ID_ATTRIBUTE = "data-chunk-id";
/** 未認識の発話の印の id（要確認の箇所への移動に使う） */
export const REVIEW_MARKER_ATTRIBUTE = "data-review-marker";
