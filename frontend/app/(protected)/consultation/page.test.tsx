import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { pushMock, replaceMock } = vi.hoisted(() => ({
  pushMock: vi.fn(),
  replaceMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, replace: replaceMock }),
}));

vi.mock(
  "@/features/consultation/components/AuthenticatedConsultationFlow",
  () => ({
    AuthenticatedConsultationFlow: ({
      onBackToNotice,
      onReturnHome,
      onOpenPlan,
      onSaveCompleted,
    }: {
      onBackToNotice: () => void;
      onReturnHome: () => void;
      onOpenPlan: () => void;
      onSaveCompleted: () => void;
    }) => (
      <div>
        <button type="button" onClick={onBackToNotice}>
          注意へ戻る
        </button>
        <button type="button" onClick={onReturnHome}>
          保存せず戻る
        </button>
        <button type="button" onClick={onOpenPlan}>
          プラン案内
        </button>
        <button type="button" onClick={onSaveCompleted}>
          保存成功
        </button>
      </div>
    ),
  }),
);

import ConsultationPage from "./page";

beforeEach(() => {
  pushMock.mockReset();
  replaceMock.mockReset();
});

describe("ConsultationPage", () => {
  it("利用前注意から相談画面へ入り、戻る操作で注意画面へ戻る", async () => {
    render(<ConsultationPage />);

    expect(
      screen.queryByRole("heading", { name: "整理メモを保存しました" }),
    ).not.toBeInTheDocument();

    await userEvent.click(
      screen.getByRole("button", { name: "注意へ戻る" }),
    );

    expect(pushMock).toHaveBeenCalledWith("/notice");
  });

  it("保存API成功後だけ固定の完了表示を出し、ホームへ戻る", async () => {
    render(<ConsultationPage />);

    await userEvent.click(screen.getByRole("button", { name: "保存成功" }));

    expect(
      screen.getByRole("heading", { name: "整理メモを保存しました" }),
    ).toBeInTheDocument();

    await userEvent.click(
      screen.getByRole("button", { name: "ホームへ戻る" }),
    );

    expect(replaceMock).toHaveBeenCalledWith("/home");
  });

  it("保存しない場合とプラン未接続時は安全にホームへ戻る", async () => {
    render(<ConsultationPage />);

    await userEvent.click(
      screen.getByRole("button", { name: "保存せず戻る" }),
    );
    await userEvent.click(
      screen.getByRole("button", { name: "プラン案内" }),
    );

    expect(replaceMock).toHaveBeenNthCalledWith(1, "/home");
    expect(replaceMock).toHaveBeenNthCalledWith(2, "/home");
  });
});
