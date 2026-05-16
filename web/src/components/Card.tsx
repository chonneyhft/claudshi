import clsx from "clsx";
import { motion } from "framer-motion";
import type { ReactNode } from "react";

type Props = {
  children: ReactNode;
  className?: string;
  delay?: number;
  hover?: boolean;
};

export function Card({ children, className, delay = 0, hover = false }: Props) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1], delay }}
      whileHover={hover ? { y: -2 } : undefined}
      className={clsx(
        "rounded-xl border border-line bg-bg-card",
        hover && "transition-colors hover:border-line/80 cursor-default",
        className
      )}
    >
      {children}
    </motion.div>
  );
}
