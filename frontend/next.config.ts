import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // next dev が AI エージェントを検知した際に frontend/AGENTS.md と
  // frontend/CLAUDE.md を自動生成する機能を無効化する。
  // このリポジトリの AI エージェント向け指示の正本はルートの CLAUDE.md であり、
  // frontend 配下に別の指示ファイルが生成されると正本と食い違うため。
  agentRules: false,
};

export default nextConfig;
