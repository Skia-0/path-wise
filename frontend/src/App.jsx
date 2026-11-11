import { useCallback, useEffect, useState } from "react";
import {
  clearToken,
  getToken,
  SESSION_EXPIRED_EVENT,
  SERVER_WAKING_EVENT,
  SERVER_READY_EVENT,
} from "./api/client";
import LoginPage from "./pages/LoginPage";
import SignupPage from "./pages/SignupPage";
import DashboardPage from "./pages/DashboardPage";
import DiagnosticPage from "./pages/DiagnosticPage";
import PracticePage from "./pages/PracticePage";
import NotesPage from "./pages/NotesPage";

export default function App() {
  const [signedIn, setSignedIn] = useState(() => Boolean(getToken()));
  const [authView, setAuthView] = useState("login");
  const [route, setRoute] = useState({ name: "dashboard" });
  const [isServerWaking, setIsServerWaking] = useState(false);

  useEffect(() => {
    function handleExpired() {
      setSignedIn(false);
      setRoute({ name: "dashboard" });
    }

    function handleServerWaking() {
      setIsServerWaking(true);
    }

    function handleServerReady() {
      setIsServerWaking(false);
    }

    window.addEventListener(SESSION_EXPIRED_EVENT, handleExpired);
    window.addEventListener(SERVER_WAKING_EVENT, handleServerWaking);
    window.addEventListener(SERVER_READY_EVENT, handleServerReady);

    return () => {
      window.removeEventListener(SESSION_EXPIRED_EVENT, handleExpired);
      window.removeEventListener(SERVER_WAKING_EVENT, handleServerWaking);
      window.removeEventListener(SERVER_READY_EVENT, handleServerReady);
    };
  }, []);

  const handleLoginSuccess = useCallback(() => {
    setSignedIn(true);
    setRoute({ name: "dashboard" });
  }, []);

  const handleSignOut = useCallback(() => {
    clearToken();
    setSignedIn(false);
    setAuthView("login");
    setRoute({ name: "dashboard" });
  }, []);

  const handleStartDiagnostic = useCallback((subject) => {
    setRoute({ name: "diagnostic", subject });
  }, []);

  const handleStartPractice = useCallback((subject) => {
    setRoute({ name: "practice", subject });
  }, []);

  const handleOpenNotes = useCallback((subject = "Core Mathematics") => {
    setRoute({ name: "notes", subject });
  }, []);

  const handleExitToDashboard = useCallback(() => {
    setRoute({ name: "dashboard" });
  }, []);

  return (
    <div className="app-root">
      {/* Server Waking Indicator Banner */}
      {isServerWaking && (
        <div className="server-waking-banner" role="status">
          <span className="waking-spinner">⚡</span>
          <span>Connecting to Path-Wise backend... (Waking up server)</span>
        </div>
      )}

      {!signedIn ? (
        authView === "signup" ? (
          <SignupPage
            onSignupSuccess={handleLoginSuccess}
            onGoToLogin={() => setAuthView("login")}
          />
        ) : (
          <LoginPage
            onLoginSuccess={handleLoginSuccess}
            onGoToSignup={() => setAuthView("signup")}
          />
        )
      ) : route.name === "diagnostic" ? (
        <DiagnosticPage
          key={`diagnostic-${route.subject}`}
          subject={route.subject}
          onExit={handleExitToDashboard}
        />
      ) : route.name === "practice" ? (
        <PracticePage
          key={`practice-${route.subject}`}
          subject={route.subject}
          onExit={handleExitToDashboard}
        />
      ) : route.name === "notes" ? (
        <NotesPage
          key={`notes-${route.subject}`}
          initialSubject={route.subject}
          onExit={handleExitToDashboard}
        />
      ) : (
        <div>
          <nav className="top-nav-bar">
            <button
              type="button"
              className="btn-ghost"
              onClick={() => handleOpenNotes()}
            >
              📖 Study Notes
            </button>
            <button
              type="button"
              className="btn-ghost text-muted"
              onClick={handleSignOut}
            >
              Sign Out
            </button>
          </nav>
          <DashboardPage
            onSignOut={handleSignOut}
            onStartDiagnostic={handleStartDiagnostic}
            onStartPractice={handleStartPractice}
          />
        </div>
      )}
    </div>
  );
}