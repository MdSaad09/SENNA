import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";

import SocBar from "./SocBar";

afterEach(cleanup);

// the fill is whichever descendant carries an inline width — the bar's one moving part
function fillOf(bar: HTMLElement): HTMLElement {
  const fill = [...bar.querySelectorAll<HTMLElement>("*")].find(
    (element) => element.style.width !== "",
  );
  if (fill === undefined) {
    throw new Error("soc-bar has no element with an inline width — the fill is missing");
  }
  return fill;
}

test("the fill width is the SOC share of the usable store", () => {
  render(<SocBar socMj={1} usableSocMj={4} />);
  const bar = screen.getByTestId("soc-bar");
  expect(fillOf(bar).style.width).toBe("25%");
  expect(bar).toHaveTextContent("1.00 / 4 MJ");
});

test("an empty store shows a zero-width fill and still prints the number", () => {
  render(<SocBar socMj={0} usableSocMj={4} />);
  const bar = screen.getByTestId("soc-bar");
  expect(fillOf(bar).style.width).toBe("0%");
  expect(bar).toHaveTextContent("0.00 / 4 MJ");
});

test("a full store fills the whole bar", () => {
  render(<SocBar socMj={4} usableSocMj={4} />);
  expect(fillOf(screen.getByTestId("soc-bar")).style.width).toBe("100%");
});
