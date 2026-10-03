import {
  type RefObject,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { MS_PER_SECOND } from "../shared/lectureStatus";
import {
  nextStep,
  outputTime,
  type Position,
  positionAt,
  type Timeline,
} from "./timeline";

const PLAY = { type: "play" } as const;

/** 再生位置を画面に知らせる間隔。フレームごとに知らせると、編集画面をフレームごとに描き直すことになる */
const REPORT_INTERVAL_MS = 50;

/** 録画ファイルを切り替えたあと、読み込めたら行うこと。 */
interface Pending {
  timeMs: number;
  play: boolean;
}

export interface Player {
  /** video 要素に付ける */
  video: RefObject<HTMLVideoElement | null>;
  /** video 要素に読ませる proxy 動画の URL */
  source: string | null;
  playing: boolean;
  /** 再生位置（録画ファイルと、その中の時刻） */
  position: Position | null;
  /** 出力（カット後）での再生位置と、全体の長さ */
  outputMs: number;
  durationMs: number;
  /** 削除区間を飛ばして再生するか */
  skipCuts: boolean;
  /** 動画を読み込めなかった */
  failed: boolean;
  toggle: () => void;
  seek: (position: Position) => void;
  seekOutput: (outputMs: number) => void;
  setSkipCuts: (skip: boolean) => void;
  /** video 要素に付ける、通知の受け口 */
  events: {
    onPlay: () => void;
    onPause: () => void;
    onEnded: () => void;
    onTimeUpdate: () => void;
    onLoadedMetadata: () => void;
    onError: () => void;
  };
}

/**
 * カット後のプレビューの再生（Design Doc 3-6）。録画ファイルごとの proxy 動画を 1 つの video 要素で切り替えながら、
 * 削除区間に入ったら次の残す区間へ飛ぶ。
 *
 * 飛ぶかどうかは、フレームごと（requestVideoFrameCallback）に確かめる（timeupdate は間隔が粗く、
 * 削除区間の頭が聞こえてしまう）。使えない環境では、timeupdate だけで確かめる。
 * proxyUrl には、呼ぶたびに変わらない関数を渡すこと。
 */
export function usePlayer(
  timeline: Timeline,
  proxyUrl: (recordingId: string) => string,
): Player {
  const video = useRef<HTMLVideoElement>(null);
  const [moved, setCurrent] = useState<Position | null>(() =>
    positionAt(timeline, 0),
  );
  // 残す区間が 1 つもない状態で開いたあと、編集で残す区間ができたら、その頭から始める
  const current = useMemo(
    () => moved ?? positionAt(timeline, 0),
    [moved, timeline],
  );
  const [playing, setPlaying] = useState(false);
  const [skipCuts, setSkipCuts] = useState(true);
  const [failed, setFailed] = useState(false);
  // 通知の受け口（tick・toggle など）は描くたびに作り直さない。動画からの通知は、描いた直後の
  // effect より先に届くことがあるので、最新の値は、描くときに ref へ書いておく
  const latest = useRef({ timeline, current, skipCuts });
  latest.current = { timeline, current, skipCuts };
  // 最初の読み込みでも、最初の残す区間の頭を出す
  const pending = useRef<Pending | null>(
    current === null ? null : { timeMs: current.timeMs, play: false },
  );

  const moveTo = useCallback((target: Position, play: boolean) => {
    const element = video.current;
    setCurrent(target);
    if (element === null) {
      return;
    }
    if (target.recordingId !== latest.current.current?.recordingId) {
      // 動画が替わる。読み込めてから（onLoadedMetadata）位置を合わせる
      pending.current = { timeMs: target.timeMs, play };
      return;
    }
    if (pending.current !== null) {
      // まだ読み込みの途中。読み込めたときに合わせる位置を、差し替える
      pending.current = {
        timeMs: target.timeMs,
        play: play || pending.current.play,
      };
      return;
    }
    element.currentTime = target.timeMs / MS_PER_SECOND;
    if (play) {
      start(element);
    }
  }, []);

  const tick = useCallback(() => {
    const element = video.current;
    const { timeline: now, current: at, skipCuts: skip } = latest.current;
    if (element === null || at === null || pending.current !== null) {
      return;
    }
    const here: Position = {
      recordingId: at.recordingId,
      timeMs: Math.round(element.currentTime * MS_PER_SECOND),
    };
    const step = !element.paused && skip ? nextStep(now, here) : PLAY;
    if (step.type === "seek") {
      moveTo({ recordingId: here.recordingId, timeMs: step.timeMs }, false);
    } else if (step.type === "switch") {
      moveTo({ recordingId: step.recordingId, timeMs: step.timeMs }, true);
    } else {
      if (step.type === "end") {
        element.pause();
      }
      setCurrent((previous) =>
        previous !== null &&
        previous.recordingId === here.recordingId &&
        Math.abs(previous.timeMs - here.timeMs) < REPORT_INTERVAL_MS
          ? previous
          : here,
      );
    }
  }, [moveTo]);

  useFrameTick(video, playing, tick);

  const toggle = useCallback(() => {
    const element = video.current;
    const { timeline: now, current: at, skipCuts: skip } = latest.current;
    if (element === null || at === null) {
      return;
    }
    if (!element.paused) {
      element.pause();
      return;
    }
    const first = positionAt(now, 0);
    if (first !== null && isFinished(now, at, skip, element.ended)) {
      moveTo(first, true);
    } else {
      start(element);
    }
  }, [moveTo]);

  const seek = useCallback(
    (target: Position) => {
      const element = video.current;
      moveTo(target, element !== null && !element.paused);
    },
    [moveTo],
  );
  const seekOutput = useCallback(
    (outputMs: number) => {
      const target = positionAt(latest.current.timeline, outputMs);
      if (target !== null) {
        seek(target);
      }
    },
    [seek],
  );

  const events = useMemo(
    () => ({
      onPlay: () => setPlaying(true),
      onPause: () => setPlaying(false),
      onEnded: () => {
        setPlaying(false);
        // 削除した部分も再生しているときは、録画ファイルの終わりで次の録画ファイルへ移る
        const { timeline: now, current: at } = latest.current;
        const next =
          at === null
            ? undefined
            : now.recordingIds[now.recordingIds.indexOf(at.recordingId) + 1];
        if (next !== undefined) {
          moveTo({ recordingId: next, timeMs: 0 }, true);
        }
      },
      onTimeUpdate: tick,
      onLoadedMetadata: () => {
        const element = video.current;
        const waiting = pending.current;
        pending.current = null;
        setFailed(false);
        if (element === null || waiting === null) {
          return;
        }
        element.currentTime = waiting.timeMs / MS_PER_SECOND;
        if (waiting.play) {
          start(element);
        }
      },
      onError: () => {
        // 読み込めなかったときは、pause の通知が来ない
        pending.current = null;
        setPlaying(false);
        setFailed(true);
      },
    }),
    [tick, moveTo],
  );

  return {
    video,
    source: current === null ? null : proxyUrl(current.recordingId),
    playing,
    position: current,
    outputMs: current === null ? 0 : outputTime(timeline, current),
    durationMs: timeline.durationMs,
    skipCuts,
    failed,
    toggle,
    seek,
    seekOutput,
    setSkipCuts,
    events,
  };
}

/**
 * 再生を始める。始められなかったとき（読み込みの失敗）は video 要素の error で分かるので、ここでは何もしない
 * （動画を切り替えた直後の中断も、ここに来る）。
 */
function start(element: HTMLVideoElement): void {
  element.play().catch(() => {});
}

/**
 * 最後まで再生したか（そのあとの「再生」は、最初から始める）。
 * 削除した部分も再生しているときは、最後の残す区間のあとにも再生するものがあるので、
 * 最後の録画ファイルの終わりまで行ったときだけ。
 */
function isFinished(
  timeline: Timeline,
  position: Position,
  skipCuts: boolean,
  ended: boolean,
): boolean {
  return skipCuts
    ? nextStep(timeline, position).type === "end"
    : ended && position.recordingId === timeline.recordingIds.at(-1);
}

/**
 * 再生中は、フレームごとに tick を呼ぶ（requestVideoFrameCallback を持つブラウザだけ。
 * 持たなければ、video 要素の timeupdate で呼ばれる分だけになる）。
 */
function useFrameTick(
  video: RefObject<HTMLVideoElement | null>,
  playing: boolean,
  tick: () => void,
): void {
  useEffect(() => {
    const element = video.current;
    if (
      !playing ||
      element === null ||
      !("requestVideoFrameCallback" in element)
    ) {
      return;
    }
    let handle = element.requestVideoFrameCallback(function onFrame() {
      tick();
      handle = element.requestVideoFrameCallback(onFrame);
    });
    return () => element.cancelVideoFrameCallback(handle);
  }, [video, playing, tick]);
}
