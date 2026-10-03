import type { components } from "./generated/schema";

type Schemas = components["schemas"];

export type LectureSummary = Schemas["LectureSummaryOut"];
export type LectureStatus = Schemas["LectureStatus"];
