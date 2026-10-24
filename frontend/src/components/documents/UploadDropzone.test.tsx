import { describe, expect, it } from "vitest";

import { validateFile } from "./UploadDropzone";

const file = (name: string, size: number, type = "application/pdf") =>
  new File([new Uint8Array(size)], name, { type });

describe("validateFile", () => {
  it("accepts a PDF under the size limit", () => {
    expect(validateFile(file("kyc.pdf", 1024), 1)).toBeNull();
  });

  it("rejects non-PDF, empty and oversized files", () => {
    expect(validateFile(file("notes.docx", 10, "application/msword"), 1)).toMatch(/Only PDF/);
    expect(validateFile(file("empty.pdf", 0), 1)).toMatch(/empty/);
    expect(validateFile(file("big.pdf", 2 * 1024 * 1024), 1)).toMatch(/larger than 1 MB/);
  });
});
