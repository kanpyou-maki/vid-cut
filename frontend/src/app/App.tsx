import { ApiProvider } from "../api/ApiContext";
import type { Api } from "../api/client";
import { EditorPage } from "../editor/EditorPage";
import { LibraryPage } from "../library/LibraryPage";
import { Link, usePathname } from "../shared/navigation";
import { LIBRARY_PATH, parseRoute, type Route } from "../shared/routes";
import styles from "./App.module.css";

/**
 * 画面の枠。api が null なのは、画面の HTML からトークンを読めなかったとき
 * （API はトークンなしでは使えないので、呼ばずに案内を出す）。
 */
export function App({ api }: { api: Api | null }) {
  const route = parseRoute(usePathname());

  return (
    <div className={appClassName(route)}>
      <header className={styles.header}>
        <h1 className={styles.title}>
          <Link to={LIBRARY_PATH}>vid-cut</Link>
        </h1>
      </header>
      <main className={styles.main}>
        {api === null ? (
          <MissingToken />
        ) : (
          <ApiProvider api={api}>
            <Page route={route} />
          </ApiProvider>
        )}
      </main>
    </div>
  );
}

/** 編集画面は、画面の高さに収める（中の文字起こしだけをスクロールさせる）。 */
function appClassName(route: Route): string {
  return route.name === "editor" ? `${styles.app} ${styles.fill}` : styles.app;
}

function Page({ route }: { route: Route }) {
  switch (route.name) {
    case "library":
      return <LibraryPage />;
    case "editor":
      // 別のレクチャーに移ったら、編集状態と履歴ごと作り直す
      return <EditorPage key={route.lectureId} lectureId={route.lectureId} />;
    case "not_found":
      return <NotFound />;
  }
}

function NotFound() {
  return (
    <section>
      <p>このページはありません</p>
      <Link to={LIBRARY_PATH}>素材一覧へ</Link>
    </section>
  );
}

function MissingToken() {
  return (
    <div role="alert">
      <p>トークンを読み取れませんでした。</p>
      <p>
        <code>vidcut serve</code>（開発中は <code>vidcut serve --dev</code>
        ）が起動していることを確かめて、ページを読み込み直してください。
      </p>
    </div>
  );
}
