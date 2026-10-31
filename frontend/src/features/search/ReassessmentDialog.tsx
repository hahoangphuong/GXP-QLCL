import type { ReactNode } from "react";
import { useCertificateDialogFocus } from "./useCertificateDialogFocus";

// The dialog lifetime owns focus; business intent remains in SearchPage.
export function ReassessmentDialog({ children }: { children: ReactNode }) {
  const ref = useCertificateDialogFocus();
  return <div className="dialog-backdrop" role="presentation">
    <section ref={ref} tabIndex={-1} aria-labelledby="reassessment-dialog-title" aria-modal="true" className="panel reassessment-dialog" role="dialog">
      {children}
    </section>
  </div>;
}
