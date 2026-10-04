import { screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/errors";
import {
  advance,
  cutTexts,
  DETAIL,
  editorApi,
  renderEditor,
  SECOND_MS,
  transcriptPane,
} from "../test/editorPage";
import {
  fakeApi,
  job,
  lectureDetail,
  recordingDetail,
  suggestion,
  tokens,
} from "../test/fakeApi";

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
});

afterEach(() => {
  vi.useRealTimers();
});

describe("EditorPage: 読み込み", () => {
  it("読み込むまでは、読み込み中であることと、素材一覧へ戻るリンクを表示する", () => {
    renderEditor(fakeApi());

    expect(screen.getByText("読み込み中…")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 2, name: "編集画面" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "素材一覧へ戻る" }),
    ).toHaveAttribute("href", "/");
  });

  it("レクチャーの id で詳細を読み、題名を見出しにする", async () => {
    const { api, getLecture } = editorApi(DETAIL);
    renderEditor(api);

    expect(
      await screen.findByRole("heading", { level: 2, name: "s05-12sample" }),
    ).toBeInTheDocument();
    expect(getLecture).toHaveBeenCalledWith("lec1", expect.any(AbortSignal));
  });

  it("プレビュー・文字起こし・波形の 3 つの場所を用意する", async () => {
    renderEditor(editorApi(DETAIL).api);
    await transcriptPane();

    expect(
      screen.getByRole("region", { name: "プレビュー" }).querySelector("video"),
    ).not.toBeNull();
    expect(screen.getByRole("region", { name: "波形" })).toHaveTextContent(
      "準備中",
    );
  });

  it("編集できる状態になったら、読み直しをやめる", async () => {
    const { api, getLecture } = editorApi(DETAIL);
    renderEditor(api);
    await transcriptPane();

    await advance(SECOND_MS * 3);

    expect(getLecture).toHaveBeenCalledTimes(1);
  });

  it("レクチャーがなければ、失敗の文と素材一覧へのリンクを表示する", async () => {
    const api = fakeApi({
      getLecture: async () => {
        throw new ApiError(
          "not_found",
          "指定されたデータが見つかりません",
          404,
        );
      },
    });
    renderEditor(api);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "指定されたデータが見つかりません",
    );
    expect(screen.queryByText("読み込み中…")).not.toBeInTheDocument();
  });

  it("読み込みに失敗しても、次の読み直しで読めれば表示する", async () => {
    const { api, getLecture } = editorApi(DETAIL);
    getLecture.mockRejectedValueOnce(
      new ApiError("unreachable", "サーバーに接続できません", null),
    );
    renderEditor(api);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "サーバーに接続できません",
    );

    await advance(SECOND_MS);

    await transcriptPane();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

describe("EditorPage: 解析・判定が済んでいないレクチャー", () => {
  const notAnalyzed = recordingDetail({
    id: "r1",
    name: "a.mov",
    analyzed: false,
  });

  it("解析中は、文字起こしを出さずに進捗を表示し、終わったら自動で表示する", async () => {
    const { api, getLecture, setDetail } = editorApi(
      lectureDetail({
        status: "analyzing",
        recordings: [notAnalyzed],
        jobs: [job({ target_id: "r1", status: "running", progress: 0.42 })],
      }),
    );
    renderEditor(api);

    expect(await screen.findByRole("status")).toHaveTextContent(
      "解析中 42%です。終わると自動で表示されます",
    );
    expect(
      screen.queryByRole("region", { name: "文字起こし" }),
    ).not.toBeInTheDocument();

    // 待っている間は、1 秒ごとに読み直す
    expect(getLecture).toHaveBeenCalledTimes(1);
    await advance(SECOND_MS);
    expect(getLecture).toHaveBeenCalledTimes(2);

    setDetail(DETAIL);
    await advance(SECOND_MS);

    await transcriptPane();
    expect(
      screen.getByRole("button", { name: "元に戻す" }),
    ).toBeInTheDocument();
  });

  it("解析が失敗していれば、失敗の定型文と、素材一覧で再実行できることを表示する", async () => {
    const { api } = editorApi(
      lectureDetail({
        status: "failed",
        recordings: [notAnalyzed],
        jobs: [
          job({
            target_id: "r1",
            status: "failed",
            error_code: "source_missing",
            error_message: "録画ファイルが見つかりません",
          }),
        ],
      }),
    );
    renderEditor(api);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(
      "解析（a.mov）に失敗しました: 録画ファイルが見つかりません",
    );
    expect(alert).toHaveTextContent("素材一覧で再実行してください");
  });

  it("解析結果が読めない録画ファイルがあれば、解析し直す必要があることを表示する", async () => {
    const { api } = editorApi(
      lectureDetail({
        recordings: [
          recordingDetail({ analyzed: false, analysis_unreadable: true }),
        ],
      }),
    );
    renderEditor(api);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "解析結果を読み取れません。解析し直す必要があります",
    );
  });

  it("判定中は、文字起こしを読み取り専用で表示し、終わったら編集できるようにする", async () => {
    const { api, setDetail } = editorApi({
      ...DETAIL,
      status: "judging",
      judged: false,
      judged_suggestions: [],
      recordings: [
        {
          ...DETAIL.recordings[0],
          suggestions: [
            suggestion({
              id: "f1",
              recording_id: "r1",
              kind: "filler",
              start_ms: 0,
              end_ms: 100,
            }),
          ],
        },
      ],
    });
    renderEditor(api);

    const pane = await transcriptPane();
    expect(screen.getByRole("status")).toHaveTextContent(
      "判定中です。終わると編集できます",
    );
    // 削除済みの部分は出すが、押して戻すことはできない
    expect(within(pane).getByTitle("フィラー")).toHaveTextContent("あ");
    expect(cutTexts()).toEqual([]);
    expect(
      screen.queryByRole("button", { name: "元に戻す" }),
    ).not.toBeInTheDocument();

    setDetail(DETAIL);
    await advance(SECOND_MS);

    expect(
      await screen.findByRole("button", { name: "元に戻す" }),
    ).toBeInTheDocument();
    expect(cutTexts()).toEqual(["かきく"]);
  });

  it("判定が失敗していれば、そのことを示したうえで編集できる", async () => {
    const { api } = editorApi({
      ...DETAIL,
      status: "failed",
      judged: false,
      judged_suggestions: [],
      jobs: [
        job({
          kind: "judge_lecture",
          target_id: "lec1",
          status: "failed",
          error_code: "login_required",
          error_message: "claude にログインしていません",
        }),
      ],
    });
    renderEditor(api);
    await transcriptPane();

    const notice = screen.getByRole("alert");
    expect(notice).toHaveTextContent(
      "言い直しの判定に失敗しました: claude にログインしていません",
    );
    expect(notice).toHaveTextContent(
      "無音とフィラーのカットだけで編集できます",
    );
    expect(
      screen.getByRole("button", { name: "元に戻す" }),
    ).toBeInTheDocument();
  });
});

describe("EditorPage: 文字起こしの表示", () => {
  it("チャンクごとの段落に、開始時刻とトークンを並べる", async () => {
    renderEditor(editorApi(DETAIL).api);
    const pane = await transcriptPane();

    const paragraphs = within(pane).getAllByRole("paragraph");
    expect(paragraphs.map((paragraph) => paragraph.textContent)).toEqual([
      "0:00あいうえお",
      "0:01かきく",
    ]);
  });

  it("削除候補のトークンを、種類を添えた削除済みの部分として表示する", async () => {
    renderEditor(editorApi(DETAIL).api);
    await transcriptPane();

    const cut = screen.getByRole("button", {
      name: "「かきく」を元に戻す（言い直し）",
    });
    expect(cut).toHaveTextContent("かきく");
    // 自動の候補の説明は、理由と一緒に出す（title は付けない。二重に出るため）
    expect(cut).not.toHaveAttribute("title");
  });

  it("戻した候補は、普通の文字として表示する", async () => {
    const { api } = editorApi({
      ...DETAIL,
      edit_state: { ...DETAIL.edit_state, restored_suggestion_ids: ["j1"] },
    });
    renderEditor(api);
    await transcriptPane();

    expect(cutTexts()).toEqual([]);
  });

  it("手動の削除区間は、手動の削除済みの部分として表示する", async () => {
    const { api } = editorApi({
      ...DETAIL,
      edit_state: {
        ...DETAIL.edit_state,
        manual_cuts: [
          { id: "m1", recording_id: "r1", start_ms: 100, end_ms: 300 },
        ],
      },
    });
    renderEditor(api);
    await transcriptPane();

    expect(
      screen.getByRole("button", { name: "「いう」を元に戻す（手動）" }),
    ).toHaveAttribute("title", "手動（クリックで元に戻す）");
  });

  it("削除の種類・戻し済み・要確認の凡例を表示する（無音は文字起こしに出さないので、載せない）", async () => {
    renderEditor(editorApi(DETAIL).api);
    await transcriptPane();

    const legend = screen.getByRole("list", { name: "削除の種類" });
    expect(
      within(legend)
        .getAllByRole("listitem")
        .map((item) => item.textContent),
    ).toEqual([
      "言い直し",
      "言い間違い",
      "雑音",
      "フィラー",
      "手動",
      "戻し済み",
      "要確認",
    ]);
  });

  it("録画ファイルが 1 本なら、ファイル名の見出しを出さない", async () => {
    renderEditor(editorApi(DETAIL).api);
    const pane = await transcriptPane();

    expect(within(pane).queryByRole("heading")).not.toBeInTheDocument();
  });

  it("まとめたレクチャーは、録画ファイルごとに番号とファイル名の見出しを挟む", async () => {
    const { api } = editorApi({
      ...DETAIL,
      recordings: [
        DETAIL.recordings[0],
        recordingDetail({
          id: "r2",
          name: "b.mov",
          tokens: tokens("c2", "さしす", 0),
        }),
      ],
    });
    renderEditor(api);
    const pane = await transcriptPane();

    expect(
      within(pane)
        .getAllByRole("heading", { level: 3 })
        .map((heading) => heading.textContent),
    ).toEqual(["1. a.mov", "2. b.mov"]);
  });

  it("文字起こしを HTML として解釈しない", async () => {
    const { api } = editorApi({
      ...DETAIL,
      title: "<b>題名</b>",
      recordings: [
        recordingDetail({
          id: "r1",
          name: "a.mov",
          tokens: [
            {
              id: "t0",
              chunk_id: "c0",
              text: "<img src=x onerror=alert(1)>",
              start_ms: 0,
              end_ms: 100,
              asr_confidence: 1,
              align_score: 1,
            },
          ],
        }),
      ],
      judged_suggestions: [],
    });
    renderEditor(api);

    expect(
      await screen.findByText("<img src=x onerror=alert(1)>"),
    ).toBeInTheDocument();
    expect(document.querySelector("img")).toBeNull();
    expect(
      screen.getByRole("heading", { level: 2, name: "<b>題名</b>" }),
    ).toBeInTheDocument();
  });
});
