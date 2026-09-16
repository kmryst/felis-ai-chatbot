import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Turbopack / output file tracing の基準ディレクトリを frontend に固定する。
  // リポジトリルートと frontend の両方に package-lock.json があるため、
  // Next.js が lockfile からワークスペースルートを推論すると
  // リポジトリルートが選ばれ、次の警告が出る。
  //   "Next.js inferred your workspace root, but it may not be correct."
  // Next.js 16 では推論されたルートが output file tracing の基準にもなり、
  // ルートがリポジトリルートだと standalone 出力が
  // .next/standalone/frontend/server.js と 1 階層深くなる。
  // frontend/Dockerfile はビルドコンテキストが frontend のみで
  // ルートの lockfile が無いため .next/standalone/server.js を前提としており、
  // ローカルビルドと構造が食い違う。ここで明示して両者を一致させる。
  // outputFileTracingRoot は設定しない。Next.js 16 では turbopack.root と
  // 同一のルートに統合されており、片方を設定すると両方に同じ値が入るため
  // （両方を異なる値で設定すると警告になる）。
  turbopack: {
    root: import.meta.dirname,
  },

  // コンテナデプロイ用に自己完結の standalone 出力を生成する（ADR-0027 決定 7。
  // frontend/Dockerfile が .next/standalone をコピーして実行する）。
  // 通常の next build / next start の動作には影響しない。
  output: "standalone",

  // next dev が AI エージェントを検知した際に frontend/AGENTS.md と
  // frontend/CLAUDE.md を自動生成する機能を無効化する。
  // このリポジトリの AI エージェント向け指示の正本はルートの CLAUDE.md であり、
  // frontend 配下に別の指示ファイルが生成されると正本と食い違うため。
  agentRules: false,
};

export default nextConfig;
