import { AnimatePresence, motion } from "framer-motion";
import { Route, Switch, useLocation } from "wouter";
import { Nav } from "./components/Nav";
import { PnlView } from "./views/PnlView";
import { PortfolioView } from "./views/PortfolioView";
import { SessionsView } from "./views/SessionsView";
import { TradesView } from "./views/TradesView";

export function App() {
  const [location] = useLocation();

  return (
    <div className="min-h-screen bg-bg text-ink">
      <Nav />
      <main className="max-w-6xl mx-auto px-6 py-10">
        <AnimatePresence mode="wait">
          <motion.div
            key={location}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
          >
            <Switch>
              <Route path="/" component={PortfolioView} />
              <Route path="/pnl" component={PnlView} />
              <Route path="/trades" component={TradesView} />
              <Route path="/sessions" component={SessionsView} />
              <Route>
                <div className="text-ink-muted">Not found.</div>
              </Route>
            </Switch>
          </motion.div>
        </AnimatePresence>
      </main>
    </div>
  );
}
