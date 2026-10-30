import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import HomePage from "./page";

describe("HomePage", () => {
  it("相談開始と保存メモ一覧への導線を表示する", () => {
    render(<HomePage />);

    expect(screen.getByRole("link", { name: "相談を始める" })).toHaveAttribute(
      "href",
      "/notice",
    );
    expect(screen.getByRole("link", { name: "保存メモを見る" })).toHaveAttribute(
      "href",
      "/memos",
    );
  });
});
