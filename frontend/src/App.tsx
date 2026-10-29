import { useState } from "react";
import { SystemBar } from "./components/SystemBar";
import { ProjectList } from "./components/ProjectList";
import { ProjectView } from "./components/ProjectView";
import { EpisodeView } from "./components/EpisodeView";

type Nav =
  | { view: "projects" }
  | { view: "project"; projectId: number }
  | { view: "episode"; projectId: number; episodeId: number };

export default function App() {
  const [nav, setNav] = useState<Nav>({ view: "projects" });

  return (
    <div className="app">
      <SystemBar onBrand={() => setNav({ view: "projects" })} />
      {nav.view === "projects" && (
        <ProjectList onOpen={(projectId) => setNav({ view: "project", projectId })} />
      )}
      {nav.view === "project" && (
        <ProjectView
          projectId={nav.projectId}
          onBack={() => setNav({ view: "projects" })}
          onOpenEpisode={(episodeId) =>
            setNav({ view: "episode", projectId: nav.projectId, episodeId })}
        />
      )}
      {nav.view === "episode" && (
        <EpisodeView
          episodeId={nav.episodeId}
          onBack={() => setNav({ view: "projects" })}
          onBackProject={(projectId) => setNav({ view: "project", projectId })}
        />
      )}
    </div>
  );
}
