"use client";
import { useActionState } from "react";
import Link from "next/link";
import { importLatestRun } from "./actions";
export default function ImportForm() {
  const [message,action,pending] = useActionState(importLatestRun, "");
  return <form action={action}><button className="primary" disabled={pending}>{pending ? "Importing…" : "Import latest screening run"}</button>
    {message && <p role="status">{message}</p>}<p><Link href="/">Open screening queue</Link></p></form>;
}
