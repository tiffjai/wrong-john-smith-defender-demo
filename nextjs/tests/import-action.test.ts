// @vitest-environment node
import { beforeEach, expect, test, vi } from "vitest";
const state = vi.hoisted(() => ({ role: "reviewer", scope: "all", user: true, readFile: vi.fn(), rpc: vi.fn() }));
vi.mock("node:fs/promises", () => ({readFile: state.readFile}));
vi.mock("next/cache", () => ({revalidatePath: vi.fn()}));
vi.mock("../lib/supabase", () => ({cloudMode:true, config:()=>({url:"https://example.supabase.co",key:"sb_publishable_test"}), serverClient:async()=>({
  auth:{getUser:async()=>({data:{user:state.user?{id:"user-1"}:null}})},
  from:()=>({select:()=>({eq:()=>({maybeSingle:async()=>({data:{booking_entity:"UK",review_role:state.role,data_scope:state.scope}})})})}),
  rpc:state.rpc,
})}));
import { importLatestRun } from "../app/admin/import-screening/actions";

beforeEach(()=>{
  vi.clearAllMocks();state.role="reviewer";state.scope="all";state.user=true;
  state.readFile.mockResolvedValue(JSON.stringify({source:"Test run",synthetic:false,traces:{},predictions:[{hit_id:"H-1",alert_id:"A-1",decision:"REVIEW",reason_code:"INSUFFICIENT_DATA",customer_record_id:null,reason:"Missing date",evidence:[]}]}));
  state.rpc.mockResolvedValue({data:{alerts:1,hits:1},error:null});
});

test("only authenticated all-data Seniors may submit an import",async()=>{
  state.user=false;expect(await importLatestRun()).toMatch(/Sign in/);
  state.user=true;state.role="analyst";expect(await importLatestRun()).toMatch(/Senior access required/);
  state.role="reviewer";state.scope="entity";expect(await importLatestRun()).toMatch(/Senior access required/);
  expect(state.rpc).not.toHaveBeenCalled();expect(state.readFile).not.toHaveBeenCalled();
});

test("repeat imports use the same content identity and preserve original findings",async()=>{
  expect(await importLatestRun()).toMatch(/Imported 1 alerts and 1 findings/);
  await importLatestRun();
  expect(state.rpc.mock.calls[0]).toEqual(state.rpc.mock.calls[1]);
  expect(state.rpc.mock.calls[0][0]).toBe("import_screening_run");
  expect(state.rpc.mock.calls[0][1].p_payload.predictions[0].decision).toBe("REVIEW");
});

test("invalid source and database failures do not report success",async()=>{
  state.readFile.mockResolvedValueOnce('{"source":"bad"}');
  expect(await importLatestRun()).toMatch(/Could not validate/);
  expect(state.rpc).not.toHaveBeenCalled();
  state.rpc.mockResolvedValueOnce({data:null,error:{message:"private error"}});
  const result=await importLatestRun();expect(result).toMatch(/no partial import/);expect(result).not.toContain("private error");
});
