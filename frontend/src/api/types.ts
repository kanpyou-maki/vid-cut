import type { components } from "./generated/schema";

type Schemas = components["schemas"];

export type LectureSummary = Schemas["LectureSummaryOut"];
export type LectureStatus = Schemas["LectureStatus"];
export type LectureRef = Schemas["LectureRefOut"];
export type Recording = Schemas["RecordingOut"];
export type Job = Schemas["JobOut"];
export type JobListItem = Schemas["JobListItemOut"];
export type FsListing = Schemas["FsListingOut"];
export type FsEntry = Schemas["FsEntryOut"];
export type ImportResult = Schemas["ImportResultOut"];
export type LectureDetail = Schemas["LectureDetailOut"];
export type RecordingDetail = Schemas["RecordingDetailOut"];
export type Chunk = Schemas["ChunkOut"];
export type Token = Schemas["TokenOut"];
export type Suggestion = Schemas["SuggestionOut"];
export type ReviewMark = Schemas["ReviewMarkOut"];
export type CutKind = Schemas["CutKind"];
export type EditState = Schemas["EditStateOut"];
export type ManualCut = Schemas["ManualCutOut"];
/** 波形のピーク値。1 秒あたり per_second 個の、0〜1 の値 */
export type Peaks = Schemas["PeaksOut"];
/** 書き出しの状態と保存先。directory と path は絶対パス */
export type Exports = Schemas["ExportsOut"];
/** 1 つの形式の書き出し先・最後に書き出した日時・最新の書き出しジョブ */
export type ExportFile = Schemas["ExportFileOut"];
export type ExportFormat = Schemas["ExportIn"]["format"];
/** 残す発話の前・後ろ・文の終わりのあとに残す余白（ミリ秒。0〜2000 の整数） */
export type KeepPadding = Schemas["KeepPaddingOut"];
/** ワークスペース全体の設定。customized は、保存した値を使っているかどうか */
export type Settings = Schemas["SettingsOut"];
/** 保存する編集状態（version は、読み込んだときの版） */
export type Edits = Schemas["EditsIn"];
