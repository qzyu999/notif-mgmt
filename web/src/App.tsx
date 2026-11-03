import { useEffect, useState } from "react";

import AppShell from "./components/AppShell";
import FollowUps from "./pages/FollowUps";
import People from "./pages/People";
import PersonDetail from "./pages/PersonDetail";
import Sources from "./pages/Sources";
import Today from "./pages/Today";

function useHashRoute(): string {
  const [hash, setHash] = useState(() => window.location.hash || "#/today");
  useEffect(() => {
    const onChange = () => setHash(window.location.hash || "#/today");
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return hash;
}

export default function App() {
  const route = useHashRoute();
  let page: React.ReactNode;
  if (route.startsWith("#/people/")) {
    page = <PersonDetail personId={Number(route.split("/")[2])} />;
  } else if (route === "#/people") {
    page = <People />;
  } else if (route === "#/followups") {
    page = <FollowUps />;
  } else if (route === "#/sources") {
    page = <Sources />;
  } else {
    page = <Today />;
  }
  return <AppShell route={route}>{page}</AppShell>;
}
