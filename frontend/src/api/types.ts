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
export type ImportFailure = Schemas["ImportFailureOut"];
