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
/** 保存する編集状態（version は、読み込んだときの版） */
export type Edits = Schemas["EditsIn"];
