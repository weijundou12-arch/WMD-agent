import { cn } from "@/lib/utils";

const toneClass = {
  strong: "bg-[#dff5e9] text-[#0c5c3d] border-[#a7ddbd]",
  moderate: "bg-[#fff2cd] text-[#7b5414] border-[#e9ca7b]",
  weak: "bg-[#fde4d9] text-[#95402a] border-[#e8a58f]",
  insufficient: "bg-[#edf0f2] text-[#4a5863] border-[#cbd3d8]",
  neutral: "bg-white text-ink border-[#d9e0dd]"
};

export function Badge({
  children,
  tone = "neutral",
  className
}: {
  children: React.ReactNode;
  tone?: keyof typeof toneClass;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md border px-2 py-1 text-xs font-semibold",
        toneClass[tone],
        className
      )}
    >
      {children}
    </span>
  );
}
