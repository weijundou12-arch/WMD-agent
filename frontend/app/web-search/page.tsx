import { Suspense } from "react";
import { ChatWorkspace } from "@/components/chat/chat-workspace";

export default function WebSearchPage() {
  return (
    <Suspense fallback={null}>
      <ChatWorkspace
        title="Web Search Agent"
        workspaceTitle="Web Search Run"
        panelTitle="Web Source Review"
        initialMode="web_search"
        lockMode
        endpoint="web"
        defaultRetrieval="advanced"
        answerOnly
        examples={[
          "德国司美格鲁肽目前多少钱？",
          "EMA 最近有没有 GLP-1 药物安全更新？",
          "2025 年以后医疗 QA Agent 有哪些最新进展？"
        ]}
        plannedSteps={[
          "Understanding question",
          "Planning online search queries",
          "Multi-provider online search",
          "Page extraction / snippets",
          "Source credibility ranking",
          "Evidence sentence extraction",
          "Cross-source verification",
          "GPT-4-style comparison",
          "Cited answer generation"
        ]}
      />
    </Suspense>
  );
}
