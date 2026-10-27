import { Suspense } from "react";
import { ChatWorkspace } from "@/components/chat/chat-workspace";

export default function MedicalRagPage() {
  return (
    <Suspense fallback={null}>
      <ChatWorkspace
        title="Medical RAG Agent"
        workspaceTitle="Literature RAG Run"
        panelTitle="Medical Evidence Review"
        initialMode="medical_rag"
        lockMode
        endpoint="medical"
        defaultRetrieval="advanced"
        answerOnly
        examples={[
          "司美格鲁肽会不会影响骨密度？",
          "HPV 与 sarcopenia 有哪些研究证据？",
          "ACL reconstruction 中机器人导航有哪些最新研究？"
        ]}
        plannedSteps={[
          "Understand medical question",
          "Rewrite clinical queries",
          "Strict PubMed + Europe PMC search",
          "BM25 + dense coarse recall",
          "Advanced rerank Top-K",
          "Weighted Evidence Gate",
          "GPT-4-style comparison",
          "Final answer synthesis"
        ]}
      />
    </Suspense>
  );
}
