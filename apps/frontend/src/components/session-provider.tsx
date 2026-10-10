"use client";

import { createContext, useContext, useEffect, useEffectEvent, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { LOGIN_PATH, sanitizeReturnTo } from "@/lib/auth-routing";
import { saveDraft } from "@/lib/form-drafts";
import type { MessageKey } from "@/lib/i18n/messages";
import { editActionClassName } from "@/lib/mobile-access";
import {
  laterStatus,
  parseSessionStatus,
  sessionPhase,
  shouldRenewOnActivity,
  type SessionPhase,
  type SessionStatus,
} from "@/lib/session-timer";
import { unsavedChanges } from "@/lib/unsaved-changes";
import { fetchSessionStatus, renewSession } from "@/services/session";

const CHANNEL = "crm-session";
const TICK_MS = 5_000;
const ACTIVITY_EVENTS = ["pointerdown", "keydown", "scroll"] as const;

const MobileReadOnly = createContext(false);

/** Wrap edit and export actions: hidden under 768 px when the admin made phones read-only. */
export function EditAction({ children }: { children: React.ReactNode }) {
  return <div className={editActionClassName(useContext(MobileReadOnly))}>{children}</div>;
}

function serialise(status: SessionStatus) {
  return {
    idle_expires_at: status.idleExpiresAt.toISOString(),
    absolute_expires_at: status.absoluteExpiresAt?.toISOString() ?? null,
    warning_seconds: status.warningSeconds,
    mobile: status.mobile,
    mobile_read_only: status.mobileReadOnly,
  };
}

export function SessionProvider({
  messages,
  children,
}: {
  messages: Record<MessageKey, string>;
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const [status, setStatus] = useState<SessionStatus | null>(null);
  const [phase, setPhase] = useState<SessionPhase>("active");
  const lastRenewal = useRef<Date | null>(null);
  const channel = useRef<BroadcastChannel | null>(null);

  function adopt(next: SessionStatus | null, broadcast: boolean) {
    if (next === null) {
      setPhase("expired");
      return;
    }
    setStatus((current) => (current ? laterStatus(current, next) : next));
    if (broadcast) {
      channel.current?.postMessage(serialise(next));
    }
  }

  const renew = async () => {
    lastRenewal.current = new Date();
    adopt(await renewSession(), true);
  };

  useEffect(() => {
    channel.current = typeof BroadcastChannel === "undefined" ? null : new BroadcastChannel(CHANNEL);
    channel.current?.addEventListener("message", (event: MessageEvent) => {
      const incoming = parseSessionStatus(event.data);
      if (incoming) {
        adopt(incoming, false);
      }
    });
    void fetchSessionStatus().then((loaded) => adopt(loaded, true));
    return () => channel.current?.close();
  }, []);

  const onActivity = useEffectEvent(() => {
    if (phase === "active" && shouldRenewOnActivity(lastRenewal.current, new Date())) {
      void renew();
    }
  });

  useEffect(() => {
    ACTIVITY_EVENTS.forEach((name) => window.addEventListener(name, onActivity, { passive: true }));
    return () => ACTIVITY_EVENTS.forEach((name) => window.removeEventListener(name, onActivity));
  }, []);

  useEffect(() => {
    if (!status) {
      return;
    }
    const tick = () => {
      const next = sessionPhase(status, new Date());
      if (next === "expired") {
        // Another tab may have kept the session alive without telling us; ask before giving up.
        void fetchSessionStatus().then((fresh) => {
          if (fresh && sessionPhase(fresh, new Date()) !== "expired") {
            adopt(fresh, false);
          } else {
            setPhase("expired");
          }
        });
        return;
      }
      setPhase(next);
    };
    tick();
    const timer = window.setInterval(tick, TICK_MS);
    return () => window.clearInterval(timer);
  }, [status]);

  useEffect(() => {
    const warnBeforeLeaving = (event: BeforeUnloadEvent) => {
      if (unsavedChanges.any()) {
        event.preventDefault();
      }
    };
    window.addEventListener("beforeunload", warnBeforeLeaving);
    return () => window.removeEventListener("beforeunload", warnBeforeLeaving);
  }, []);

  useEffect(() => {
    if (phase === "expired") {
      const drafts = unsavedChanges.drafts();
      if (Object.keys(drafts).length > 0) {
        saveDraft(window.localStorage, pathname, drafts);
      }
    }
  }, [phase, pathname]);

  const signInAgain = () => {
    const loginUrl = new URL(LOGIN_PATH, window.location.origin);
    loginUrl.searchParams.set("next", sanitizeReturnTo(`${window.location.pathname}${window.location.search}`));
    window.location.replace(loginUrl.toString());
  };

  return (
    <MobileReadOnly.Provider value={status?.mobileReadOnly ?? false}>
      {children}
      <AlertDialog open={phase === "warning"}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{messages["session.warningTitle"]}</AlertDialogTitle>
            <AlertDialogDescription>{messages["session.warningDescription"]}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogAction onClick={() => void renew()}>{messages["session.stay"]}</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      <AlertDialog open={phase === "expired"}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{messages["session.expiredTitle"]}</AlertDialogTitle>
            <AlertDialogDescription>{messages["session.expiredDescription"]}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogAction onClick={signInAgain}>{messages["session.signIn"]}</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </MobileReadOnly.Provider>
  );
}
