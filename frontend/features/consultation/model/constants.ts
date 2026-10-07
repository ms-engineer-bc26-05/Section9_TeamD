import type {
  EmotionCategory,
  GuidedTopic,
  HandlingType,
  ThemeCategory,
} from "./contracts";

interface SelectionOption<T extends string> {
  value: T;
  label: string;
  description?: string;
}

export const THEME_OPTIONS = [
  {
    value: "communication",
    label: "会話・連絡・愛情表現",
    description: "会話の量、連絡の頻度、愛情表現など",
  },
  {
    value: "lifestyle",
    label: "暮らし・家事・生活習慣",
    description: "家事の分担、生活リズム、過ごし方など",
  },
  {
    value: "money",
    label: "お金の感覚の違い",
    description: "使い方、貯め方、負担の分け方など",
  },
  {
    value: "care",
    label: "気遣い・思いやりの伝わり方",
    description: "気にかけてほしいこと、支え方の違いなど",
  },
  {
    value: "future",
    label: "将来・価値観・二人の関係",
    description: "将来像、結婚、仕事、家族、関係のあり方など",
  },
  {
    value: "other",
    label: "その他",
    description: "当てはまるものがない、まだよく分からない場合",
  },
] as const satisfies readonly SelectionOption<ThemeCategory>[];

export const EMOTION_OPTIONS = [
  { value: "lonely", label: "寂しい" },
  { value: "sad", label: "悲しい" },
  { value: "anxious", label: "不安" },
  { value: "angry", label: "怒り・いら立ち" },
  { value: "confused", label: "モヤモヤ・違和感" },
  { value: "hurt", label: "傷ついた" },
  { value: "self_blame", label: "自分を責める気持ち（情けなさ・罪悪感）" },
  { value: "other", label: "その他・まだよく分からない" },
] as const satisfies readonly SelectionOption<EmotionCategory>[];

export const HANDLING_OPTIONS = [
  { value: "tell", label: "伝える" },
  { value: "hold", label: "今は保留する" },
  { value: "not_tell", label: "伝えない" },
] as const satisfies readonly SelectionOption<HandlingType>[];

export const GUIDED_TOPIC_LABELS: Record<GuidedTopic, string> = {
  true_feeling: "本音",
  background: "背景",
  wish: "望み",
};
