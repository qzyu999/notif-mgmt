import { useEffect, useState } from "react";

import People from "./pages/People";
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
    page = <p>Person detail arrives in the next milestone.</p>;
  } else if (route === "#/people") {
    page = <People />;
  } else if (route === "#/followups") {
    page = <p>Follow-ups arrive in the next milestone.</p>;
  } else if (route === "#/sources") {
    page = <p>Sources arrive in the next milestone.</p>;
  } else {
    page = <Today />;
  }
  return (
    <div>
      <nav aria-label="Primary">
        <a href="#/today">Today</a> <a href="#/people">People</a>{" "}
        <a href="#/followups">Follow-ups</a> <a href="#/sources">Sources</a>
      </nav>
      {page}
    </div>
  );
}
