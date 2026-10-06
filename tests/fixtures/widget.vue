<template>
  <!-- Render the widget container -->
  <div class="widget">
    <!-- Show the title -->
    <h1>{{ title }}</h1>
    <a href="https://example.com//docs">docs</a>
  </div>
</template>

<script lang="ts">
// Import the defineComponent helper
import { defineComponent } from "vue";

export default defineComponent({
  // Define the component props
  props: { title: String },
  // eslint-disable-next-line vue/no-unused-properties
  data() {
    // Return the initial state
    return { count: 0 };
  },
});
</script>

<style>
/* Style the widget container */
.widget {
  /* Set the background color to white */
  background: #fff; /* white */
}
</style>
